import logging
import config
import time
import datetime
from .observer import Observer
from .emailer import send_email
from fiatconverter import FiatConverter
from private_markets import huobicny,okcoincny
from dbmanage import dbmanage
class TraderBot(Observer):
    def __init__(self):
        self.clients = {
            # TODO: move that to the config file
            # "BitstampUSD": bitstampusd.PrivateBitstampUSD(),
            "HuobiCNY":huobicny.PrivateHuobiCNY(),
            "OKCoinCNY":okcoincny.PrivateOkCoinCNY()
        }
        self.fc = FiatConverter()
        self.trade_wait = config.trade_wait  # in seconds
        self.last_trade = 0
        self.lastTradeType=0  # 0 waitting; 1: buy at huobi sell at ok; 2:buy at ok and sell at huobi  
        self.potential_trades = []
        self.update_balance()
        self.profit=0
        self.exeInfo=''
        self.db=dbmanage('sqlite3.db')
    def get_observer_name(self):
        return 'TraderBot'
    def begin_opportunity_finder(self, depths):
        self.potential_trades = []

    def end_opportunity_finder(self):
        if not self.potential_trades:
            return
        self.potential_trades.sort(key=lambda x: x[0])
        # Execute only the best (more profitable)
        self.execute_trade(*self.potential_trades[0][1:])
        return True

    def get_min_tradeable_volume(self, buyprice, usd_bal, btc_bal):
        min1 = float(usd_bal) / ((1 + config.balance_margin) * buyprice)
        min2 = float(btc_bal) / (1 + config.balance_margin)
        return min(min1, min2)

    def update_balance(self):
        for kclient in self.clients:
            self.clients[kclient].get_info()
    def get_client_balance(self):
        retVal={'HuobiCNY':{ 'cny':self.clients['HuobiCNY'].cny_balance, 'btc': self.clients['HuobiCNY'].btc_balance,'asset':self.clients['HuobiCNY'].netAsset,'loanBtc':self.clients['HuobiCNY'].loanBtc},\
                'OKCoinCNY':{ 'cny':self.clients['OKCoinCNY'].cny_balance, 'btc': self.clients['OKCoinCNY'].btc_balance,'asset':self.clients['OKCoinCNY'].netAsset,'loanBtc':self.clients['OKCoinCNY'].loanBtc}}
        return retVal
    def opportunity(self, profit, volume, buyprice, kask, sellprice, kbid, perc,
                    weighted_buyprice, weighted_sellprice):
        #if  profit < config.profit_thresh or perc*sellprice < config.perc_thresh:
        if volume<0.25:# or perc*sellprice<0.2:
            logging.verbose("[TraderBot] Profit or profit percentage lower than"+
                            " thresholds")
            return
        if kask not in self.clients:
            logging.warn("[TraderBot] Can't automate this trade, client not "+
                         "available: %s" % kask)
            return
        if kbid not in self.clients:
            logging.warn("[TraderBot] Can't automate this trade, " +
                         "client not available: %s" % kbid)
            return
        volume = min(config.max_tx_volume, volume)


        max_volume = self.get_min_tradeable_volume(buyprice,
                                                   self.clients[kask].cny_balance,
                                                   self.clients[kbid].btc_balance)
        volume = min(volume, max_volume, config.max_tx_volume)
        if volume < config.min_tx_volume:
            logging.warn("Can't automate this trade, minimum volume transaction"+
                         " not reached %f/%f" % (volume, config.min_tx_volume))
            logging.warn("Balance on %s: %f USD - Balance on %s: %f BTC"
                         % (kask, self.clients[kask].cny_balance, kbid,
                            self.clients[kbid].btc_balance))
            return
        current_time = time.time()
        if current_time - self.last_trade < self.trade_wait:
            logging.warn("[TraderBot] Can't automate this trade, last trade " +
                         "occured %.2f seconds ago" %
                         (current_time - self.last_trade))
            return
        self.potential_trades.append([profit, volume, kask, kbid,
                                      weighted_buyprice, weighted_sellprice,
                                      buyprice, sellprice])

    def watch_balances(self):
        pass

    def excute_to_balance(self,volume,price,tradetype,extrangename):
        if tradetype=='buy':
            self.clients[extrangename].buy(volume,price)
        elif tradetype=='sell':
            self.clients[extrangename].sell(volume,price)

    def execute_trade(self, volume, kask, kbid, weighted_buyprice,
                      weighted_sellprice, buyprice, sellprice):
        self.last_trade = time.time()
        logging.info("Buy @%s %f BTC and sell @%s" % (kask, volume, kbid))
        #self.clients[kask].marketBuy(float(format(volume*buyprice,'.2f')))
        #self.clients[kbid].marketSell(float(format(volume,'.4f')))
        #self.clients[kask].buy(volume, buyprice)
        #self.clients[kbid].sell(volume, sellprice)
        sellExePrice=0;
        buyExePrice=0;
        currentProfit=0
        curtimeStr=""
   
        volume=float(format(volume,'.4f'))
        buyprice=float(format(buyprice,'.2f'))
        sellprice=float(format(sellprice,'.2f'))

        buyOrderId=self.clients[kask].buy(volume, buyprice+3)
        sellOrderId=self.clients[kbid].sell(volume, sellprice-3)
        #buyOrderId=1746867081
        if buyOrderId:
            buyExeInfo=self.clients[kask].orderInfo(buyOrderId)
            buyExePrice=float(buyExeInfo['avg_price'])

        #sellOrderId=5026388552
        if sellOrderId:
            sellExeInfo = self.clients[kbid].orderInfo(sellOrderId)
            sellExePrice=float(sellExeInfo['avg_price'])

        if kbid=='HuobiCNY' and kask=='OKCoinCNY':
            self.lastTradeType=1
        elif kbid=='OKCoinCNY' and kask=='HuobiCNY':
            self.lastTradeType=2

        if sellExePrice and buyExePrice:
            currentProfit=sellExePrice*volume-buyExePrice*volume
            self.profit+=currentProfit
            curtimeStr=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            totolAsset= self.clients['HuobiCNY'].netAsset + self.clients['OKCoinCNY'].netAsset
            str="[%s] TrdeVolume:%f  Buy @%s price %f and sell @%s price %f  currentProfit= %f [%f]  TOTALASSET=%f\n" \
                          % (curtimeStr, volume,kask,buyExePrice,kbid,sellExePrice,currentProfit,self.profit,totolAsset)
            print(str)
            self.exeInfo+= str
        self.update_balance()
        self.get_client_balance()
        priceinfoLastUpadte=self.db.get_lastuptate_time()
        tradeinfo={}
        tradeinfo['TIME']=priceinfoLastUpadte
        tradeinfo['CUR_LOGTIME']=curtimeStr
        tradeinfo['ASK_MARKET']=kask
        tradeinfo['BID_MARKET']=kbid
        tradeinfo['BUY_PRICE']=buyExePrice
        tradeinfo['SELL_PRICE']=sellExePrice
        tradeinfo['BUY_PLANPRICE']=buyprice
        tradeinfo['SELL_PLANPRICE']=sellprice
        tradeinfo['BUY_AMOUNT']=volume
        tradeinfo['SELL_AMOUNT']=volume
        tradeinfo['CUR_PROFIT']=float(format(currentProfit,'.2f'))
        tradeinfo['TOTOL_PROFIT']=float(format(self.profit,'.2f'))
        self.db.update_tradeinfo(tradeinfo)
    def getTotalprofit(self):
        return self.exeInfo
        #return self.profit
import logging
import config
import time
import datetime
from .observer import Observer
from .emailer import send_email
from fiatconverter import FiatConverter
from private_markets import huobicny,okcoincny
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

    def opportunity(self, profit, volume, buyprice, kask, sellprice, kbid, perc,
                    weighted_buyprice, weighted_sellprice):
        if  profit < config.profit_thresh or perc*sellprice < config.perc_thresh:
        #if volume<0.08 or perc*sellprice<0.2:
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

        volume=float(format(volume,'.4f'))
        buyprice=float(format(buyprice,'.2f'))
        sellprice=float(format(sellprice,'.2f'))

        buyOrderId=self.clients[kask].buy(volume, buyprice)
        #buyOrderId=1746867081
        if buyOrderId:
            buyExeInfo=self.clients[kask].orderInfo(buyOrderId)
            buyExePrice=float(buyExeInfo['avg_price'])

        sellOrderId=self.clients[kbid].sell(volume, sellprice)
        #sellOrderId=5026388552
        if sellOrderId:
            sellExeInfo = self.clients[kbid].orderInfo(sellOrderId)
            sellExePrice=float(sellExeInfo['avg_price'])

        if kbid=='HuobiCNY' and kask=='OKCoinCNY':
            self.lastTradeType=1
        elif kbid=='OKCoinCNY' and kask=='HuobiCNY':
            self.lastTradeType=2

        if sellExePrice and buyExePrice:
            self.profit+=sellExePrice*volume-buyExePrice*volume
            curtimeStr=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            str="[%s] TrdeVolume:%f  Buy @%s price %f and sell @%s price %f [%f]\n" % (curtimeStr, volume,kask,buyExePrice,kbid,sellExePrice,self.profit)
            print(str)
            self.exeInfo+= str
    def getTotalprofit(self):
        return self.exeInfo
        #return self.profit
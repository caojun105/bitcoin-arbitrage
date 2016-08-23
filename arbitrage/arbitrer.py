# Copyright (C) 2013, Maxime Biais <maxime@biais.org>

import public_markets
import observers
import config
import time
import logging
import json
import sys
from concurrent.futures import ThreadPoolExecutor, wait
import os
import traceback
import datetime
class Arbitrer(object):
    def assure_path_exists(self,path):
        os.makedirs(path, exist_ok=True)
        #dir=os.path.abspath(__file__)
        #if not os.path.exists(dir):
                #os.makedirs(dir)

    def __init__(self):
        self.markets = []
        self.observers = []
        self.depths = {}
        self.dumpTickData=config.DUMP_TICKER
        self.dumpTickDepth=config.DUMP_TICKER_DEPTH
        self.init_markets(config.markets)
        self.init_observers(config.observers)
        self.threadpool = ThreadPoolExecutor(max_workers=10)
        self.last_depth_update=0
        self.depthJsonFileDic='depth_json'
        self.tickDataFileDic='tikcer'
        self.tickDepthFileDic='tickDepth'
        self.accountInfoDumpDic ='dump'
        self.assure_path_exists(self.depthJsonFileDic)
        self.assure_path_exists(self.tickDataFileDic)
        self.assure_path_exists(self.accountInfoDumpDic)
        self.tickerdata=[]
        self.tickThereHold=[]
        self.tickGap={}
        self.tickAndDepth=[]
        self.exeStart=False
    def dump_depth(self,depthdata):
        curtimeStr=datetime.datetime.now().strftime("%Y-%m-%d")
        filepath=os.path.join(self.tickDataFileDic,curtimeStr)  ## accroding to the date to dump information
        self.assure_path_exists(filepath)
        fp= os.path.join(filepath,str(int(time.time()))+'.json')
        with open(fp,'w') as f:
            json.dump(depthdata,f)
    def dump_tickdepth(self,tickdepthdata):
        curtimeStr=datetime.datetime.now().strftime("%Y-%m-%d")
        filepath=os.path.join(self.tickDepthFileDic,curtimeStr)  ## accroding to the date to dump information
        self.assure_path_exists(filepath)
        fp= os.path.join(filepath,str(int(time.time()))+'.json')
        with open(fp,'w') as f:
            json.dump(tickdepthdata,f)
    def dumpInfo(self):
        fp= os.path.join(self.accountInfoDumpDic,str(int(time.time()))+'.txt')
        profit=0
        for observer in self.observers:
            if observer.get_observer_name()=='TraderBot':
                   profit = observer.getTotalprofit()      

        ####################implement later
        with open(fp,'w') as f:
            f.write(str(profit))
            #f.write('ssss')
            f.close()
            #f.write(str(profit))
    def init_markets(self, markets):
        self.market_names = markets
        for market_name in markets:
            try:
                exec('import public_markets.' + market_name.lower())
                market = eval('public_markets.' + market_name.lower() + '.' +
                              market_name + '()')
                self.markets.append(market)
            except (ImportError, AttributeError) as e:
                print("%s market name is invalid: Ignored (you should check your config file)" % (market_name))

    def init_observers(self, _observers):
        self.observer_names = _observers
        for observer_name in _observers:
            try:
                exec('import observers.' + observer_name.lower())
                observer = eval('observers.' + observer_name.lower() + '.' +
                                observer_name + '()')
                self.observers.append(observer)
            except (ImportError, AttributeError) as e:
                print("%s observer name is invalid: Ignored (you should check your config file)" % (observer_name))

    def get_profit_for(self, mi, mj, kask, kbid):
        if self.depths[kask]["asks"][mi]["price"] \
           >= self.depths[kbid]["bids"][mj]["price"]:
            return 0, 0, 0, 0

        max_amount_buy = 0
        for i in range(mi + 1):
            max_amount_buy += self.depths[kask]["asks"][i]["amount"]
        max_amount_sell = 0
        for j in range(mj + 1):
            max_amount_sell += self.depths[kbid]["bids"][j]["amount"]
        max_amount = min(max_amount_buy, max_amount_sell, config.max_tx_volume)

        buy_total = 0
        w_buyprice = 0
        for i in range(mi + 1):
            price = self.depths[kask]["asks"][i]["price"]
            amount = min(max_amount, buy_total + self.depths[
                         kask]["asks"][i]["amount"]) - buy_total
            if amount <= 0:
                break
            buy_total += amount
            if w_buyprice == 0:
                w_buyprice = price
            else:
                w_buyprice = (w_buyprice * (
                    buy_total - amount) + price * amount) / buy_total

        sell_total = 0
        w_sellprice = 0
        for j in range(mj + 1):
            price = self.depths[kbid]["bids"][j]["price"]
            amount = min(max_amount, sell_total + self.depths[
                         kbid]["bids"][j]["amount"]) - sell_total
            if amount < 0:
                break
            sell_total += amount
            if w_sellprice == 0 or sell_total == 0:
                w_sellprice = price
            else:
                w_sellprice = (w_sellprice * (
                    sell_total - amount) + price * amount) / sell_total

        profit = sell_total * w_sellprice - buy_total * w_buyprice
        return profit, sell_total, w_buyprice, w_sellprice

    def get_max_depth(self, kask, kbid):
        i = 0
        if len(self.depths[kbid]["bids"]) != 0 and \
           len(self.depths[kask]["asks"]) != 0:
            while self.depths[kask]["asks"][i]["price"] \
                  < self.depths[kbid]["bids"][0]["price"]:
                if i >= len(self.depths[kask]["asks"]) - 1:
                    break
                i += 1
        j = 0
        if len(self.depths[kask]["asks"]) != 0 and \
           len(self.depths[kbid]["bids"]) != 0:
            while self.depths[kask]["asks"][0]["price"] \
                  < self.depths[kbid]["bids"][j]["price"]:
                if j >= len(self.depths[kbid]["bids"]) - 1:
                    break
                j += 1
        return i, j

    def arbitrage_depth_opportunity(self, kask, kbid):
        #maxi, maxj = self.get_max_depth(kask, kbid)
        askIndex=0
        bidIndex=0
        buyamount=0
        sellamount=0
        buyCost=0
        sellCost=0
        tradePrice=0
        buyAveragePrice=0
        sellAveragePrice=0

        while(self.depths[kask]["asks"][askIndex]['price']\
            < self.depths[kbid]["bids"][bidIndex]['price']):
            try:
                if buyamount<sellamount:
                    buyamount=buyamount+self.depths[kask]["asks"][askIndex]['amount']
                    buyCost+= self.depths[kask]["asks"][askIndex]['amount'] * self.depths[kask]["asks"][askIndex]['price']
                    askIndex+=1

                    tradePrice=self.depths[kbid]["bids"][bidIndex]['price']
                    if askIndex>=len(self.depths[kask]["asks"]):
                        break
                else:
                    sellCost+=self.depths[kbid]["bids"][bidIndex]['amount']*self.depths[kbid]["bids"][bidIndex]['price']
                    sellamount=sellamount+self.depths[kbid]["bids"][bidIndex]['amount']
                    test=sellCost/sellamount
                    bidIndex+=1
                    tradePrice=self.depths[kask]["asks"][askIndex]['price']
                    if bidIndex>=len(self.depths[kbid]["bids"]):
                        break
            except Exception as ex:
                logging.warn("depth fail%s" % ex)
                t,v,tb = sys.exc_info()
                #traceback.print_exc()

        if buyamount!=0:
            buyAveragePrice=buyCost/buyamount
        if sellamount!=0:
            sellAveragePrice=sellCost/sellamount

        tradeAmount=min(buyamount,sellamount)
        maxProfit=(sellAveragePrice-buyAveragePrice)*tradeAmount
        return maxProfit,tradeAmount,\
            tradePrice,tradePrice,\
            buyAveragePrice,sellAveragePrice
    def arbitrage_depth_opportunity_offset(self, kask, kbid,offset):
        #maxi, maxj = self.get_max_depth(kask, kbid)
        askIndex=0
        bidIndex=0
        buyamount=0
        sellamount=0
        buyCost=0
        sellCost=0
        tradePrice=0
        buyAveragePrice=0
        sellAveragePrice=0
        try:
            while(self.depths[kask]["asks"][askIndex]['price']\
                < self.depths[kbid]["bids"][bidIndex]['price']+offset):
                    if buyamount<sellamount:
                        buyamount=buyamount+self.depths[kask]["asks"][askIndex]['amount']
                        buyCost+= self.depths[kask]["asks"][askIndex]['amount'] * self.depths[kask]["asks"][askIndex]['price']
                        askIndex+=1
                        tradeBuyPrice=self.depths[kask]["asks"][askIndex]['price']
                        tradeSellPrice=self.depths[kbid]["bids"][bidIndex]['price']
                        #if askIndex>=len(self.depths[kask]["asks"]):
                            #break
                    else:
                        sellCost+=self.depths[kbid]["bids"][bidIndex]['amount']*self.depths[kbid]["bids"][bidIndex]['price']
                        sellamount=sellamount+self.depths[kbid]["bids"][bidIndex]['amount']
                        test=sellCost/sellamount
                        bidIndex+=1
                        tradeBuyPrice=self.depths[kask]["asks"][askIndex]['price']
                        tradeSellPrice=self.depths[kbid]["bids"][bidIndex]['price']
                        #if bidIndex>=len(self.depths[kbid]["bids"]):
                            #break
                    if bidIndex>=len(self.depths[kbid]["bids"]) or askIndex>=len(self.depths[kask]["asks"]):
                        break
        except Exception as ex:
                logging.warn("depth fail%s" % ex)
                logging.warn("bidindex=%d,askindex=%d,bid=%s,aks=%s,lenask=%d,lenBid=%d"%(bidIndex,\
                    askIndex,kbid,kask,len(self.depths[kask]["asks"]),len(self.depths[kbid]["bids"])))
                return 0,0,0,0,0,0
        if buyamount!=0:
            buyAveragePrice=buyCost/buyamount
        if sellamount!=0:
            sellAveragePrice=sellCost/sellamount

        tradeAmount=min(buyamount,sellamount)
        ### the profit is adjusted
        maxProfit=(sellAveragePrice+offset-buyAveragePrice)*tradeAmount  
        return maxProfit,tradeAmount,\
            tradeBuyPrice,tradeSellPrice,\
            buyAveragePrice,sellAveragePrice
    def arbitrage_opportunity2(self, kask, ask, kbid, bid):
        #print("===>arbitrage")
        perc = (bid["price"] - ask["price"]) / bid["price"] * 100
        #print(time.time())
        profit, volume, buyprice, sellprice, weighted_buyprice,\
            weighted_sellprice = self.arbitrage_depth_opportunity(kask, kbid)
        if volume == 0 or buyprice == 0:
            return
        perc2 = (1 - (volume - (profit / buyprice)) / volume) * 100
        for observer in self.observers:
            observer.opportunity(
                profit, volume, buyprice, kask, sellprice, kbid,
                perc2, weighted_buyprice, weighted_sellprice)
    def arbitrage_opportunity(self, kask, ask, kbid, bid):
        #print("===>arbitrage")
        #lastime=time.time();
        perc = (bid["price"] - ask["price"]) / bid["price"] * 100
        #print(time.time())
                
        
        profit, volume, buyprice, sellprice, weighted_buyprice,\
            weighted_sellprice = self.arbitrage_depth_opportunity(kask, kbid)
        #print("333344444====================%f"%(time.time()-lastime))
        lastime=time.time();
        if volume == 0 or buyprice == 0:
            return
        perc2 = (1 - (volume - (profit / buyprice)) / volume) * 100
        for observer in self.observers:
            observer.opportunity(
                profit, volume, buyprice, kask, sellprice, kbid,
                perc2, weighted_buyprice, weighted_sellprice)
        #print("3********************=%f"%(time.time()-lastime))

    def arbitrage_opportunity_offset(self, kask, ask, kbid, bid,offset):
        #print("===>arbitrage")
        #lastime=time.time();
        ## bid price is adjusted
        perc = (bid["price"]+ offset - ask["price"]) / bid["price"] * 100
        #print(time.time())
                
        ###means bid maket is plus the offset
        profit, volume, buyprice, sellprice, weighted_buyprice,\
            weighted_sellprice = self.arbitrage_depth_opportunity_offset(kask, kbid,offset)
        #print("333344444====================%f"%(time.time()-lastime))
        lastime=time.time();
        if volume == 0 or buyprice == 0:
            return
        perc2 = (1 - (volume - (profit / buyprice)) / volume) * 100
        for observer in self.observers:
            observer.opportunity(
                profit, volume, buyprice, kask, sellprice, kbid,
                perc2, weighted_buyprice, weighted_sellprice)
        #print("3********************=%f"%(time.time()-lastime))
    def arbitrage_depth_opportunity2(self, kask, kbid):
        maxi, maxj = self.get_max_depth(kask, kbid)
        best_profit = 0
        best_i, best_j = (0, 0)
        best_w_buyprice, best_w_sellprice = (0, 0)
        best_volume = 0
        for i in range(maxi + 1):
            for j in range(maxj + 1):
                profit, volume, w_buyprice, w_sellprice = self.get_profit_for(
                    i, j, kask, kbid)
                if profit >= 0 and profit >= best_profit:
                    best_profit = profit
                    best_volume = volume
                    best_i, best_j = (i, j)
                    best_w_buyprice, best_w_sellprice = (
                        w_buyprice, w_sellprice)
        return best_profit, best_volume, \
               self.depths[kask]["asks"][best_i]["price"], \
               self.depths[kbid]["bids"][best_j]["price"], \
               best_w_buyprice, best_w_sellprice
    def __get_market_depth(self, market, depths):
        depths[market.name] = market.get_depth()

    def update_depths(self):
        depths = {}
        futures = []
        self.last_depth_update=time.time()
        for market in self.markets:
            futures.append(self.threadpool.submit(self.__get_market_depth,
                                                  market, depths))
        wait(futures, timeout=20)
        return depths
    def get_tickdata(self):
        tmptick={}
        for market in self.markets:
            
            tmpstr=market.name
            tmptick[tmpstr]=market.get_tick_timestamp()
        return tmptick

    def tickers(self):
        tmptick={}
        for market in self.markets:      
            tmpstr=market.name
            tmptick[tmpstr]=market.get_ticker()
        return tmptick
            #return market.get_ticker()
            #logging.verbose("ticker: " + market.name + " - " + str(
               # market.get_ticker()))

    def replay_history(self, directory):
        import os
        import json
        import pprint
        files = os.listdir(directory)
        files.sort()
        for f in files:
            if ".json" not in f:
                continue
            print(f)
            jsonhandle=open(directory + '/' + f, 'r')
            print(type(jsonhandle))
            depths = json.load(jsonhandle)
            self.depths = {}
            for market in self.market_names:
                if market in depths:
                    self.depths[market] = depths[market]
            self.tick()

    def tick(self):
        #lastime=time.time()
        #print("======**%s"%time.time())
        for observer in self.observers:
            observer.begin_opportunity_finder(self.depths)

        for kmarket1 in self.depths:
            for kmarket2 in self.depths:
                ##print(kmarket1,kmarket2)
                if kmarket1 == kmarket2:  # same market
                    continue
                market1 = self.depths[kmarket1]
                market2 = self.depths[kmarket2]
                if market1["asks"] and market2["bids"] \
                   and len(market1["asks"]) > 0 and len(market2["bids"]) > 0:

                    if float(market1["asks"][0]['price']) \
                       < float(market2["bids"][0]['price']):
                        print(time.time())
                        self.arbitrage_opportunity(kmarket1, market1["asks"][0],
                                       kmarket2, market2["bids"][0])
                        #print(time.time())
                        #print("%s===="%(time.time()-lastime))
        
        if time.time()-self.last_depth_update>0.2:
            return  
        for observer in self.observers:
            if(observer.end_opportunity_finder()):
                self.dump_depth(self.depths)
    
    def tick_offset(self):
        for observer in self.observers:
            observer.begin_opportunity_finder(self.depths)

        for kmarket1 in self.depths:
            for kmarket2 in self.depths:
                ##print(kmarket1,kmarket2)
                if kmarket1 == kmarket2:  # same market
                    continue
                market1 = self.depths[kmarket1]
                market2 = self.depths[kmarket2]
                if market1["asks"] and market2["bids"] \
                   and len(market1["asks"]) > 0 and len(market2["bids"]) > 0:
                    if (kmarket1=='HuobiCNY') and (kmarket2=='OKCoinCNY'):##buy@HB and sell@OK
                         offset=self.tickGap['hb']

                    elif (kmarket1=='OKCoinCNY') and (kmarket2=='HuobiCNY'):
                         offset= -self.tickGap['ok']
                    if float(market1["asks"][0]['price']) \
                       < float(market2["bids"][0]['price']+offset):
                        self.arbitrage_opportunity_offset(kmarket1, market1["asks"][0],
                                       kmarket2, market2["bids"][0],offset)

        # if current time has elapsed many, return and do nothing.
        if time.time()-self.last_depth_update>0.2:
            return  
        for observer in self.observers:
            if(observer.end_opportunity_finder()):
                print('k')
                #self.dump_depth(self.depths)
    def calGapOffset(self,tickData):
        okdata=float(tickData['OKCoinCNY']['ticker']['last'])
        hbdata=float(tickData['HuobiCNY']['ticker']['last'])
        if len(self.tickThereHold)<150 :
            self.tickThereHold.append(hbdata-okdata)
            return 0,0
        else:
            self.exeStart=True
            del self.tickThereHold[0]
            self.tickThereHold.append(hbdata-okdata)
            tmp=self.tickThereHold[:]
            tmp.sort()
            return tmp[15],tmp[len(self.tickThereHold)-15]

    def loop(self):
        looptime=0
        while True:
            try:
                if self.dumpTickData or self.dumpTickDepth:
                    looptime=looptime+1
                    tmpTickData=self.get_tickdata()
                    hboffset,okoffset =self.calGapOffset(tmpTickData)
                    if (self.exeStart==False):
                        continue
                    self.tickGap={'hb':hboffset,'ok':okoffset}
                    self.tickerdata.append(tmpTickData)

                for observer in self.observers:
                    if observer.get_observer_name()=='TraderBot':
                        observer.update_balance()            
                self.depths = self.update_depths()
                if self.dumpTickDepth:
                    tmpTickDepthData={'tick':tmpTickData,'depth':self.depths}
                    self.tickAndDepth.append(tmpTickDepthData)
                self.tick_offset()
                if looptime>250:
                    if self.dumpTickData or self.dumpTickDepth:
                        self.dump_depth(self.tickerdata)
                        self.tickerdata=[]
                    if self.dumpTickDepth:
                        self.dump_tickdepth(self.tickAndDepth)
                        self.tickAndDepth=[]
                    looptime=0
                time.sleep(config.refresh_rate)
            except KeyboardInterrupt:
                pass
            except  Exception as ex:
                print("erro :%s[retry]" % ex)

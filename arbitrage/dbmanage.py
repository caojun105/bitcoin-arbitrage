import sqlite3

class Singleton(type):
    def __init__(self, *args, **kwargs):
        self.__instance = None
        super().__init__(*args, **kwargs)

    def __call__(self, *args, **kwargs):
        if self.__instance is None:
            self.__instance = super().__call__(*args, **kwargs)
            return self.__instance
        else:
            return self.__instance
class dbmanage(metaclass=Singleton):
    def __init__(self,db):
        self.conn = sqlite3.connect(db)

        #conn.excute("CREATE TABLE IF NOT EXIST PRICEINFO ")
        sql_create_priceinfo_tbl=""" CREATE TABLE IF NOT EXISTS PRICEINFO(
                                            TIME TEXT PRIMARY KEY NOT NULL,
                                            CUR_LOGTIME TEXT,
                                            OKPRICE float NOT NULL,
                                            HBPRICE float NOT NULL,
                                            OK_BTC float NOT NULL,
                                            OK_ASSET float NOT NULL,
                                            HB_BTC float NOT NULL,
                                            HB_ASSET float NOT NULL,
                                            TOTAL_ASSET float NOT NULL,
                                            LOW_OFFSET float NOT NULL,
                                            HIGH_OFFSET float      
                                     );"""
        sql_create_tradeinfo_tbl=""" CREATE TABLE IF NOT EXISTS TRADEINFO(
                                            TIME TEXT PRIMARY KEY NOT NULL,
                                            CUR_LOGTIME TEXT,
                                            ASK_MARKET TEXT NOT NULL,
                                            BID_MARKET TEXT NOT NULL,
                                            BUY_PRICE float NOT NULL,
                                            BUY_AMOUNT float,
                                            SELL_PRICE float NOT NULL,
                                            SELL_AMOUNT float,
                                            BUY_PLANPRICE float,
                                            SELL_PLANPRICE float,
                                            CUR_PROFIT float,
                                            TOTOL_PROFIT float
                                     );"""
        self.conn.execute(sql_create_priceinfo_tbl)
        self.conn.execute(sql_create_tradeinfo_tbl)
        self.cur = self.conn.cursor()
        self.lastupdate=0

    def __del__(self):
        self.conn.commit()
        self.conn.close()

    def update_priceinfo(self,tick):
        #insert_sql_priceinfo=""" INSERT INFO PRICEINFO (TIME,OKPRICE,HBPRICE) VALUES(?,?,?)"""\
                                       # %(tick['time'],tick['okprice'],tick['hbprice'])
        
        self.cur.execute("""INSERT INTO priceinfo (TIME,CUR_LOGTIME,OKPRICE,HBPRICE,HB_BTC,HB_ASSET,OK_BTC,OK_ASSET,TOTAL_ASSET,LOW_OFFSET,HIGH_OFFSET) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",\
                         (tick['time'],tick['cur_logtime'],tick['okprice'],tick['hbprice'],tick['hb_btc'],tick['hb_asset'],tick['ok_btc'],tick['ok_asset'],tick['totoal_asset'],tick['low_offset'],tick['high_offset']))
        self.lastupdate=tick['time']
    def update_tradeinfo(self,tradeinfo):
          self.cur.execute("""INSERT INTO TRADEINFO (TIME,CUR_LOGTIME,ASK_MARKET,BID_MARKET,BUY_PRICE,BUY_AMOUNT,SELL_PRICE,SELL_AMOUNT,BUY_PLANPRICE,SELL_PLANPRICE,CUR_PROFIT,TOTOL_PROFIT) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",\
                         (tradeinfo['TIME'],tradeinfo['CUR_LOGTIME'],tradeinfo['ASK_MARKET'],tradeinfo['BID_MARKET'],tradeinfo['BUY_PRICE'],tradeinfo['BUY_AMOUNT'],tradeinfo['SELL_PRICE'],tradeinfo['SELL_AMOUNT'],tradeinfo['BUY_PLANPRICE'],tradeinfo['SELL_PLANPRICE'],tradeinfo['CUR_PROFIT'],tradeinfo['TOTOL_PROFIT']))
    def get_lastuptate_time(self):
        return self.lastupdate
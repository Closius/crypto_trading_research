import matplotlib.pyplot as plt
import pandas as pd
import ccxt
import math
import datetime
import concurrent.futures
import traceback
import os 


pairs = ["GMX/USDT", 
"BCH/USDT", 
"ETC/USDT", 
"HBAR/USDT", 
"ILV/USDT", 
"TRB/USDT", 
"ETH/USDT", 
"ADA/USDT", 
"NEO/USDT", 
"SAND/USDT", 
"TON/USDT", 
"RUNE/USDT", 
"FIL/USDT", 
"NEAR/USDT", 
"MKR/USDT", 
"LINK/USDT", 
"ATOM/USDT", 
"BSV/USDT", 
"UNI/USDT", 
"LTC/USDT", 
"AAVE/USDT", 
"COMP/USDT", 
"SUSHI/USDT", 
"ZRO/USDT", 
"SOL/USDT", 
"CRV/USDT", 
"BTC/USDT"]
timeframe = "5m"

if timeframe[-1] != "m":
    raise ValueError('timeframe[-1] != "m"')

tf_milliseconds = int(timeframe[:-1]) * 60000

n_periods = 300
limit = 12

if timeframe[-1] != "m":
    raise ValueError('timeframe[-1] != "m"')

tf_milliseconds = int(timeframe[:-1]) * 60000

pairs_lim = pairs[:1]



def gg(pair, period, timeframe, limit):
    exchange = ccxt.binance()
    if timeframe[-1] != "m":
        raise ValueError('timeframe[-1] != "m"')
    tf_milliseconds = int(timeframe[:-1]) * 60000
    # since = exchange.milliseconds () - 86400000  # -1 day from now
    since = exchange.milliseconds () - (tf_milliseconds * limit * period)
    ohlcv = exchange.fetch_ohlcv(pair, timeframe, since=since, limit=limit)
    df_orig = pd.DataFrame(ohlcv, columns=["TIME", "OPEN", "HIGH", "LOW", "CLOSE", "VOLUME"]).drop('TIME', axis=1)
    
    # normalize by columns
    df = pd.DataFrame(columns=df_orig.columns.to_list())
    for c in df_orig:
        # minmax
        # df[c]=(df_orig[c] - df_orig[c].mean()) / (df_orig[c].max() - df_orig[c].min())
        # Z-normalization
        df[c]=(df_orig[c] - df_orig[c].mean()) / df_orig[c].std()

    df["OPEN-CLOSE"] = abs(df['OPEN'] - df['CLOSE'])
    df["HIGH-LOW"] = abs(df['HIGH'] - df['LOW'])
    corr = df.corr().drop(["OPEN", "HIGH", "LOW", "CLOSE", "VOLUME"], axis=1)
    lst = [corr['OPEN-CLOSE']['VOLUME'], corr['HIGH-LOW']['VOLUME'], corr['OPEN-CLOSE']['HIGH-LOW'], df["OPEN-CLOSE"].std(), df["HIGH-LOW"].std()]

    return pair, period, lst




out_pair_1 = {pair: pd.DataFrame(columns=['corr(O-C->V)', 'corr(H-L->V)', 'corr(O-C->H-L)', 'std(O-C)', 'std(H-L)']) for pair in pairs_lim}

def future_is_done(future):
    try:
        __pair, __period, lst = future.result()
        out_pair_1[__pair].loc[__period] = lst
    except Exception as ex:
        print(ex)

if __name__ == '__main__':

    with concurrent.futures.ProcessPoolExecutor(max_workers=os.cpu_count()) as executor:
        for _pair in pairs_lim:
            for _period in range(1, n_periods+1): # period = from 1 to n_periods
                future = executor.submit(
                    gg,
                    **{
                        "pair": _pair,
                        "period": _period,
                        "timeframe": timeframe,
                        "limit": limit,
                    },
                )
                future.add_done_callback(future_is_done)



    pairs_lim = list(out_pair_1.keys())
    # (rows, columns)
    layout = [math.ceil(len(pairs_lim) / 3), 3]
    fig, axes = plt.subplots(nrows=layout[0], ncols=layout[1])#, width_ratios=2, height_ratios=2)
    fig.set_size_inches(w=1760/100, h=layout[0]*640/100)
    fig.suptitle(f'data (y) depending on the period (x) from earliest to oldest. each x point is calculated by {limit} candles')
    axe = axes.ravel()
    for pair, ax in zip(pairs_lim, axe):
        out_pair_1[pair].plot(kind='line', title=pair, ax=ax, grid=True)
    plt.show()
    # plt.savefig(f'p_{n_periods}_lim_{limit}_newest_to_oldest.pdf')
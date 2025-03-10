"""
arbitrage between stocks. distributed deposit
"""

import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import itertools
import math
import time
import json5
import multiprocessing as mp
from multiprocessing.sharedctypes import Array

import matplotlib as mpl

# mpl.rcParams["lines.linewidth"] = 1

import mp_logging


def visualize_line_by_line(data_dict, file_name):
    """
    data_dict: {pair: df}
    """
    pairs_lim = list(data_dict.keys())
    # (rows, columns)
    layout = [math.ceil(len(pairs_lim) / 1), 1]
    fig, axes = plt.subplots(nrows=layout[0], ncols=layout[1], sharex=True)
    fig.set_size_inches(w=1760 / 100, h=layout[0] * 640 / 100)
    fig.subplots_adjust(hspace=0)
    if isinstance(axes, np.ndarray):
        axe = axes.ravel()
    else:
        axe = [axes]

    for pair, ax in zip(pairs_lim, axe):
        ax.set_xticklabels([])
        ax.tick_params(left=False, bottom=False)

        ax.set_xticks(np.arange(0, data_dict[pair].size, 1))
        ax.set_title(pair)

        data_dict[pair].plot(kind="line", ax=ax, grid=True)

    # plt.show()
    plt.savefig(f"{file_name}.pdf")


def in_process_get_ohlcv(
    stock_name, request: mp.Array, response: mp.Queue, stop_event: mp.Event, is_ready_event: mp.Event, logging_queue
):
    """
    In a separate process. Collect ohlcv for the pair, timeframe, limit (since now) in `request`
    from `stock_name` and send it through the queue `response`
    """
    import ccxt
    from ccxt.base.errors import BadSymbol

    mp_logging.LoggerWorker().logger_worker_configure(logging_queue)
    logger = mp_logging.LoggerWorker().getLogger(__name__)
    ex = getattr(ccxt, stock_name)()

    logger.info(f"{stock_name} 'ohlcv' started warmed.. ")

    is_ready_event.set()

    last_pair = b""
    while not stop_event.is_set():
        if request.value != last_pair:
            data = json5.loads(request.value.decode("utf-8"))
            try:

                if data["timeframe"][-1] != "m":
                    raise ValueError('timeframe[-1] != "m"')

                tf_milliseconds = int(data["timeframe"][:-1]) * 60000
                # since = exchange.milliseconds () - 86400000  # -1 day from now
                since = ex.milliseconds() - (tf_milliseconds * data["limit"])
                ohlcv = ex.fetch_ohlcv(data["pair"], data["timeframe"], since=since, limit=data["limit"])

            except BadSymbol:
                logger.error(f"bad symbol {data['pair']}")
                ohlcv = []
            response.put((stock_name, ohlcv, time.time()))
            last_pair = request.value


def ohlcv(stock_names, pairs, timeframe, limit, stop_event, logging_queue):
    """
    Collect ohlcv from different stocks in parallel (multiple processes)
    """
    logger = mp_logging.LoggerWorker().getLogger(__name__)
    logger.info("start 'ohlcv'")
    request = Array("c", 1000)
    request.value = b""
    response = mp.Queue()
    is_ready_event_dict = {}
    processes = []
    for stock_name in stock_names:
        is_ready_event_dict[stock_name] = mp.Event()
        p = mp.Process(
            target=in_process_get_ohlcv,
            kwargs={
                "stock_name": stock_name,
                "request": request,
                "response": response,
                "stop_event": stop_event,
                "is_ready_event": is_ready_event_dict[stock_name],
                "logging_queue": logging_queue,
            },
        )
        p.start()
        processes.append(p)

    # wait for process to warmup
    for stock_name in stock_names:
        is_ready_event_dict[stock_name].wait()

    def get_ohlcv(pair) -> pd.DataFrame:
        d = json5.dumps({"pair": pair, "timeframe": timeframe, "limit": limit})
        logger.info(f"collecting {pair}")
        request.value = bytes(d, "utf-8")
        stock_names_check = stock_names.copy()
        big_df = pd.DataFrame()
        while stock_names_check:
            stock_name, ohlcv, t = response.get(block=True)
            df = pd.DataFrame(ohlcv, columns=["TIME", "OPEN", "HIGH", "LOW", "CLOSE", "VOLUME"]).drop("TIME", axis=1)
            # df["TIME"] = pd.to_datetime(df["TIME"], unit="ms")

            # df.set_index("TIME")
            big_df[stock_name + "_CLOSE"] = df["CLOSE"]
            stock_names_check.remove(stock_name)
        big_df = big_df[sorted(big_df.columns.tolist())]

        return big_df

    p_data = {}
    for pair in pairs:
        p_data[pair] = get_ohlcv(pair)

    visualize_line_by_line(p_data, f"arbitrage_price_{timeframe}_{limit}.pdf")

    p_data_dif = {}
    for pair in pairs:
        df = pd.DataFrame()
        base_column = "bybit_CLOSE"
        for column in p_data[pair].columns.tolist():
            df[column] = p_data[pair][base_column] - p_data[pair][column]

        p_data_dif[pair] = df

    visualize_line_by_line(p_data_dif, f"arbitrage_dif_{timeframe}_{limit}.pdf")

    return p_data


def number_of_intersections(price1: pd.Series, price2: pd.Series):
    df_diff = price2 - price1

    def number_of_netavive_to_positive_switches(df: np.array):
        price_1 = df[0]
        price_2 = df[-1]
        if (price_1 < 0 and price_2 > 0) or (price_1 > 0 and price_2 < 0):
            return 1
        return 0

    noi = int(df_diff.rolling(window=2).apply(number_of_netavive_to_positive_switches, raw=True).sum())

    def less_0(df: np.array):
        price_1 = df[0]
        price_2 = df[-1]
        if price_1 < 0 and price_2 < 0:
            return 1
        return 0

    less_zero = int(df_diff.rolling(window=2).apply(less_0, raw=True).sum())

    def more_0(df: np.array):
        price_1 = df[0]
        price_2 = df[-1]
        if price_1 > 0 and price_2 > 0:
            return 1
        return 0

    more_zero = int(df_diff.rolling(window=2).apply(more_0, raw=True).sum())

    common_nonsero = df_diff.isnull().sum() / noi

    dur_up = 2 - (common_nonsero / more_zero)
    dur_down = 2 - (common_nonsero / less_zero)

    dur_up = round(float(dur_up), 2)
    dur_down = round(float(dur_down), 2)

    score = (abs(dur_up) + abs(dur_down)) / 2

    return noi, dur_up, dur_down, score


def main():
    logger_listener = mp_logging.LoggerListener()
    logging_queue = logger_listener.start_listener_process(log_file_path="arbitrage_pair_wings.log")
    logger = mp_logging.LoggerWorker().getLogger(__name__)
    logger.info("start")

    stop_event = mp.Event()

    timeframe = "1m"
    limit = 60

    stock_names = {"binance", "bybit"}  # , "htx", "mexc", "okx", "kucoin"}

    pairs = [
        "GMX/USDT",  # ]
        "BCH/USDT",
        "ETC/USDT",
        "HBAR/USDT",
        "ETH/USDT",
        "ADA/USDT",
        "SAND/USDT",
        "TON/USDT",
        "FIL/USDT",
        "NEAR/USDT",
        "MKR/USDT",
        "LINK/USDT",
        "ATOM/USDT",
        "UNI/USDT",
        "LTC/USDT",
        "AAVE/USDT",
        "COMP/USDT",
        "SUSHI/USDT",
        "ZRO/USDT",
        "SOL/USDT",
        "CRV/USDT",
        "BTC/USDT",
    ]

    # prices(stock_names, stop_event, logging_queue)
    p_data = ohlcv(
        stock_names=stock_names,
        pairs=pairs,
        timeframe=timeframe,
        limit=limit,
        stop_event=stop_event,
        logging_queue=logging_queue,
    )

    rank_by_stocks = {}  # pair: {(stock_name_1, stock_name_2): rank}
    for pair in pairs:
        logger.info(pair)
        rank_by_stocks[pair] = []
        for sn1, sn2 in itertools.combinations(stock_names, 2):
            # if p_data[pair][sn1 + "_CLOSE"].isnull().sum() != p_data[pair][sn2 + "_CLOSE"].isnull().sum():
            #     continue
            noi, dur_up, dur_down, score = number_of_intersections(
                p_data[pair][sn1 + "_CLOSE"], p_data[pair][sn2 + "_CLOSE"]
            )
            rank_by_stocks[pair].append((sn1, sn2, noi, dur_up, dur_down, score))
        rank_by_stocks[pair].sort(key=lambda x: x[5], reverse=False)
        for sns_noi in rank_by_stocks[pair]:
            logger.info(f"\t{sns_noi}")

    # show first pair
    pair = pairs[0]
    two_stocks_df = {}
    for sn1, sn2, *opt in rank_by_stocks[pair]:
        two_stocks_df[sn1 + " " + sn2 + " " + str(opt)] = pd.concat(
            [p_data[pair][sn1 + "_CLOSE"], p_data[pair][sn2 + "_CLOSE"]], axis=1
        )

    visualize_line_by_line(two_stocks_df, f"arbitrage_two_stocks_{pair.replace('/','_')}_{timeframe}_{limit}.pdf")

    stop_event.set()
    logger_listener.stop_listener_process()


if __name__ == "__main__":
    main()

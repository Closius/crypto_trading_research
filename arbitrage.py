"""
arbitrage between stocks
"""

import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import math
import time
import json5
import multiprocessing as mp
from multiprocessing.sharedctypes import Array

import matplotlib as mpl

mpl.rcParams["lines.linewidth"] = 1

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

        ax.set_xticks(np.arange(0, data_dict[pair].size, 5))
        ax.set_title(pair)

        data_dict[pair].plot(kind="line", ax=ax, grid=True)

    # plt.show()
    plt.savefig(f"{file_name}.pdf")


def in_process_get_price(
    stock_name, request: mp.Array, response: mp.Queue, stop_event: mp.Event, is_ready_event: mp.Event, logging_queue
):
    """
    In a separate process. Collect price for the pair in `request`
    from `stock_name` and send it through the queue `response`
    """
    import ccxt
    from ccxt.base.errors import BadSymbol

    mp_logging.LoggerWorker().logger_worker_configure(logging_queue)
    logger = mp_logging.LoggerWorker().getLogger(__name__)
    ex = getattr(ccxt, stock_name)()

    logger.info(f"{stock_name} 'price' started warmed.. ")

    is_ready_event.set()

    last_pair = b""
    while not stop_event.is_set():
        if request.value != last_pair:
            pair = request.value.decode("utf-8")
            try:
                pr = ex.fetch_ticker(pair)["last"]
            except BadSymbol:
                logger.error(f"bad symbol {pair}")
                pr = 0
            response.put((stock_name, pr, time.time()))
            last_pair = request.value


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


def prices(stock_names, stop_event, logging_queue):
    """
    Collect prices from different stocks in parallel (multiple processes)
    """
    logger = mp_logging.LoggerWorker().getLogger(__name__)
    logger.info("start 'prices'")
    request = Array("c", 100)
    request.value = b""
    response = mp.Queue()
    is_ready_event_dict = {}
    processes = []
    for stock_name in stock_names:
        is_ready_event_dict[stock_name] = mp.Event()
        p = mp.Process(
            target=in_process_get_price,
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

    def get_prices(pair):
        request.value = bytes(pair, "utf-8")
        logger.info(f"prices {pair}:")
        stock_names_check = stock_names.copy()
        p_pr = {}
        prices = []
        while stock_names_check:
            stock_name, price, t = response.get(block=True)
            p_pr[stock_name] = (price, t)
            prices.append(price)
            stock_names_check.remove(stock_name)
        for stock_name in stock_names:
            logger.info(f"\t {p_pr[stock_name][0]} \t {p_pr[stock_name][1]} \t {stock_name}")
        logger.info(f"\t diff: {max(prices) - min(prices)}")

    pairs = [
        "GMX/USDT",
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

    get_prices("BTC/USDT")  # just warmup

    for pair in pairs:
        get_prices(pair)


def ohlcv(stock_names, timeframe, limit, stop_event, logging_queue):
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


def main():
    logger_listener = mp_logging.LoggerListener()
    logging_queue = logger_listener.start_listener_process(log_file_path="arbitrage.log")
    logger = mp_logging.LoggerWorker().getLogger(__name__)
    logger.info("start")

    stop_event = mp.Event()

    stock_names = {"binance", "bybit", "htx", "mexc", "okx", "kucoin"}

    # prices(stock_names, stop_event, logging_queue)
    ohlcv(stock_names=stock_names, timeframe="1m", limit=30, stop_event=stop_event, logging_queue=logging_queue)

    stop_event.set()
    logger_listener.stop_listener_process()


if __name__ == "__main__":
    main()

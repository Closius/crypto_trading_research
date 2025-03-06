"""
arbitrage between stocks
"""
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import ccxt
import math
import datetime
import time
import os
import concurrent.futures
import multiprocessing as mp
from multiprocessing.sharedctypes import Value, Array

import mp_logging


def in_process_get_price(stock_name, request: mp.Array, response: mp.Queue, stop_event: mp.Event, is_ready_event: mp.Event, logging_queue):
    import ccxt
    from ccxt.base.errors import BadSymbol
    mp_logging.LoggerWorker().logger_worker_configure(logging_queue)
    logger = mp_logging.LoggerWorker().getLogger(__name__)
    ex = getattr(ccxt, stock_name)()

    logger.info(f"{stock_name} started warmed.. ")

    is_ready_event.set()

    last_pair = b"----------"
    while not stop_event.is_set():
        if request.value != last_pair:
            pair = request.value.decode("utf-8")
            try:
                pr = ex.fetch_ticker(pair)['last']
            except BadSymbol:
                logger.error(f"bad symbol {pair}")
                pr = 0
            response.put((stock_name, pr, time.time()))
            last_pair = request.value


def main():
    logger_listener = mp_logging.LoggerListener()
    logging_queue = logger_listener.start_listener_process(log_file_path="arbitrage.log")
    logger = mp_logging.LoggerWorker().getLogger(__name__)
    logger.info("start")

    stop_event = mp.Event()

    request = Array('c', b'----------')
    response = mp.Queue()

    stock_names = {"binance", "bybit", "htx", "mexc", "okx", "kucoin"}

    is_ready_event_dict = {}
    processes = []
    for stock_name in stock_names:
        is_ready_event_dict[stock_name] = mp.Event()
        p = mp.Process(target=in_process_get_price, kwargs={
                "stock_name": stock_name,
                "request": request,
                "response": response,
                "stop_event": stop_event,
                "is_ready_event": is_ready_event_dict[stock_name],
                "logging_queue": logging_queue,
        })
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

    pairs = ["GMX/USDT",
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
             "BTC/USDT"]


    get_prices("BTC/USDT") # just warmup

    for pair in pairs:
        get_prices(pair)


    stop_event.set()
    logger_listener.stop_listener_process()


if __name__ == '__main__':
    main()
"""
under construction...

arbitrage between pairs in one stock. triangular arbitrage
"""

import ccxt
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import math
import time
import json5
import threading

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


def get_pairs_no_USDT_spot():
    exchange = ccxt.binance()
    markets = exchange.fetch_markets()

    pairs_USDT = []
    for market in markets:
        if market["spot"] and market["type"] == "spot":
            symbol = market["symbol"]
            if "/" not in symbol:
                continue
            if "USDC" in symbol:
                continue
            if "USDT" in symbol:
                pairs_USDT.append(symbol)

    pairs_no_USDT = []
    for market in markets:
        if market["spot"] and market["type"] == "spot":
            symbol = market["symbol"]
            if "/" not in symbol:
                continue
            if "USDC" in symbol:
                continue
            if "EUR" in symbol:
                continue
            if "USDT" not in symbol:
                pairs_no_USDT.append(symbol)

    return pairs_USDT, pairs_no_USDT


def main():
    logger_listener = mp_logging.LoggerListener()
    logging_queue = logger_listener.start_listener_process(log_file_path="arbitrage_pairs.log")
    logger = mp_logging.LoggerWorker().getLogger(__name__)
    logger.info("start")

    stop_event = threading.Event()

    # exchange = ccxt.bybit()
    # markets = exchange.fetch_markets()
    # logger.info(json5.dumps(markets, indent=4))

    pairs_USDT, pairs_no_USDT = get_pairs_no_USDT_spot()
    print("")
    print("")
    print("")
    print("")
    print("pairs_USDT")
    print(pairs_USDT)
    print("")
    print("")
    print("")
    print("")
    print("pairs_no_USDT")
    print(pairs_no_USDT)

    stop_event.set()
    logger_listener.stop_listener_process()


if __name__ == "__main__":
    main()

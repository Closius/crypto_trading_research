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


import mp_logging

import sequence_calculator


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


def get_pairs_no_USDT_spot(stock_name):
    exchange = getattr(ccxt, stock_name)()
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
    logging_queue = logger_listener.start_listener_process(log_file_path="arbitrage_triangular.log")
    logger = mp_logging.LoggerWorker().getLogger(__name__)
    logger.info("start")

    stock_name = "binance"

    logger.info(f"stock_name: {stock_name}")
    pairs_USDT, pairs_no_USDT = get_pairs_no_USDT_spot(stock_name)
    logger.info(f"pairs_USDT size: {len(pairs_USDT)}")
    logger.info(f"pairs_no_USDT size: {len(pairs_no_USDT)}")

    sequences, uniq_pairs = sequence_calculator.sequence_calculator(
        pairs_no_USDT, start_coin="BTC", end_coin="TRUMP", max_depth=2
    )

    logger_listener.stop_listener_process()


if __name__ == "__main__":
    main()

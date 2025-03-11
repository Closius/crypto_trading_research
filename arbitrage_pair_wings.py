"""
arbitrage between stocks. distributed deposit
"""

import os

import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import itertools
import math
import time
import json5
import multiprocessing as mp
from multiprocessing.sharedctypes import Array

from pypdf import PdfWriter

import mp_logging


def visualize_line_by_line(data_dict, file_name, data_dict_helped=None, data_dict_volumes=None, highlite_zero_x=False):
    """
    data_dict: {pair: df}  - pairs data to show
    data_dict_helped: {pair: df}  - pairs data to help
    """

    def batch(iterable, n=1):
        l = len(iterable)
        for ndx in range(0, l, n):
            up = min(ndx + n, l)
            yield ndx, up, iterable[ndx:up]

    pairs_all = sorted(list(data_dict.keys()))

    files = []
    for f, t, pairs_lim in batch(pairs_all, 1):

        # (rows, columns)
        if data_dict_volumes:
            layout = [len(pairs_lim) * 2, 1]
        else:
            layout = [len(pairs_lim), 1]
        fig, axes = plt.subplots(nrows=layout[0], ncols=layout[1])  # , sharex=True)
        fig.set_size_inches(w=1760 / 100, h=layout[0] * 640 / 100)
        fig.subplots_adjust(hspace=0)
        if isinstance(axes, np.ndarray):
            axe = axes.ravel()
        else:
            axe = [axes]

        i = 0
        for pair in pairs_lim:

            if data_dict_volumes:
                ax_price = axe[i]
                ax_volume = axe[i + 1]
                i += 2
            else:
                ax_price = axe[i]
                ax_volume = None
                i += 1

            # plot prices
            ax_price.set_xticklabels([])
            ax_price.tick_params(left=False, bottom=False)

            ax_price.set_xticks(np.arange(0, data_dict[pair].size, 5))
            ax_price.set_title(pair)
            if highlite_zero_x:
                ax_price.axhline(0, color="black", linewidth=2)

            data_dict[pair].plot(kind="line", ax=ax_price, grid=True)

            # annotate with last price
            if data_dict_helped:
                for column in data_dict[pair].columns.tolist():
                    y = np.nan
                    y_text = np.nan
                    j = 0
                    while np.isnan(y) or np.isnan(y_text):
                        j -= 1
                        x = data_dict[pair].index[j]
                        y = data_dict[pair][column].iloc[j]
                        y_text = data_dict_helped[pair][column].iloc[j]

                    ax_price.annotate(y_text, (x, y))

            # plot volumes
            if data_dict_volumes:
                ax_volume.set_xticklabels([])
                ax_volume.tick_params(left=False, bottom=False)

                ax_volume.set_yscale("log")

                ax_volume.set_xticks(np.arange(0, data_dict_volumes[pair].size, 5))
                ax_volume.set_title(pair + " VOLUMES")
                data_dict_volumes[pair].plot(kind="line", ax=ax_volume, grid=True)

                d = data_dict_volumes[pair].index
                for column in data_dict_volumes[pair].columns.tolist():
                    ax_volume.fill_between(
                        d,
                        data_dict_volumes[pair][column],
                        alpha=0.2,
                        interpolate=True,
                    )

        # plt.show()
        fig.tight_layout()
        files.append(f"{file_name}_{f+1}_{t}.pdf")
        fig.savefig(files[-1], bbox_inches="tight")

    if files and os.path.exists(f"{file_name}.pdf"):
        os.remove(f"{file_name}.pdf")
    if len(files) > 1:
        merger = PdfWriter()

        for pdf in files:
            merger.append(pdf)

        merger.write(f"{file_name}.pdf")
        merger.close()

        for file in files:
            os.remove(file)
    elif len(files) == 1:
        os.rename(files[0], f"{file_name}.pdf")


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

    def get_ohlcv(pair) -> (pd.DataFrame, pd.DataFrame):
        d = json5.dumps({"pair": pair, "timeframe": timeframe, "limit": limit})
        request.value = bytes(d, "utf-8")
        stock_names_check = stock_names.copy()
        big_df = pd.DataFrame()
        big_df_vol = pd.DataFrame()
        while stock_names_check:
            stock_name, ohlcv, t = response.get(block=True)
            if ohlcv:
                df = pd.DataFrame(ohlcv, columns=["TIME", "OPEN", "HIGH", "LOW", "CLOSE", "VOLUME"]).drop(
                    "TIME", axis=1
                )
                # df["TIME"] = pd.to_datetime(df["TIME"], unit="ms")

                # df.set_index("TIME")
                big_df[stock_name + "_CLOSE"] = df["CLOSE"]
                big_df_vol[stock_name + "_VOLUME"] = df["VOLUME"]
            stock_names_check.remove(stock_name)
        big_df = big_df[sorted(big_df.columns.tolist())]
        big_df_vol = big_df_vol[sorted(big_df_vol.columns.tolist())]

        return big_df, big_df_vol

    p_data = {}
    p_data_vol = {}
    for i, pair in enumerate(pairs):
        logger.info(f"collecting {i+1} of {len(pairs)}: {pair}")
        p_data[pair], p_data_vol[pair] = get_ohlcv(pair)

    visualize_line_by_line(
        p_data,
        data_dict_volumes=p_data_vol,
        data_dict_helped=p_data,
        file_name=f"arbitrage_all_price_{timeframe}_{limit}",
    )

    p_data_dif_percent = {}
    for i, pair in enumerate(pairs):
        df_percent = pd.DataFrame()
        base_column = "bybit_CLOSE"
        for column in p_data[pair].columns.tolist():
            if "VOLUME" not in column:
                df_percent[column] = (
                    (p_data[pair][base_column] - p_data[pair][column]) / p_data[pair][base_column]
                ) * 100
            else:
                df_percent[column] = p_data[pair][column]

        p_data_dif_percent[pair] = df_percent

    visualize_line_by_line(
        p_data_dif_percent,
        data_dict_volumes=p_data_vol,
        data_dict_helped=p_data,
        file_name=f"arbitrage_all_diff_percent_{timeframe}_{limit}",
        highlite_zero_x=True,
    )

    return p_data


def find_best_stocks_pair(stock_names, pairs, timeframe, limit, p_data):
    """
    Investigate which pair of stocks give better arbitrage
    """

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

        common_nonzero = df_diff.notna().sum()

        dur_up = 2 - (common_nonzero / more_zero)
        dur_down = 2 - (common_nonzero / less_zero)

        dur_up = round(float(dur_up), 2)
        dur_down = round(float(dur_down), 2)

        score = round((abs(dur_up) + abs(dur_down)) / 2, 2)

        return {
            "noi": noi,
            "score": score,
            "common_nonzero": int(common_nonzero),
            "more_zero": int(more_zero),
            "less_zero": int(less_zero),
        }

    logger = mp_logging.LoggerWorker().getLogger(__name__)
    rank_by_stocks = {}  # pair: {(stock_name_1, stock_name_2): rank}
    for pair in pairs:
        logger.info(pair)
        rank_by_stocks[pair] = []
        for sn1, sn2 in itertools.combinations(stock_names, 2):
            # if p_data[pair][sn1 + "_CLOSE"].isnull().sum() != p_data[pair][sn2 + "_CLOSE"].isnull().sum():
            #     continue
            params = number_of_intersections(p_data[pair][sn1 + "_CLOSE"], p_data[pair][sn2 + "_CLOSE"])
            rank_by_stocks[pair].append((sn1, sn2, params))
        rank_by_stocks[pair].sort(key=lambda x: x[2]["score"], reverse=False)
        for sns_noi in rank_by_stocks[pair]:
            logger.info(f"\t{sns_noi}")

    # show first pair
    # pair = pairs[0]
    for pair in pairs:
        two_stocks_df_dif = {}
        two_stocks_df = {}
        for sn1, sn2, params in rank_by_stocks[pair]:
            two_stocks_df_dif[sn2 + " - " + sn1 + " " + str(params)] = (
                p_data[pair][sn2 + "_CLOSE"] - p_data[pair][sn1 + "_CLOSE"]
            )
            two_stocks_df[sn2 + " - " + sn1 + " " + str(params)] = (
                (p_data[pair][sn2 + "_CLOSE"] - p_data[pair][sn1 + "_CLOSE"]) / p_data[pair][sn2 + "_CLOSE"]
            ) * 100

        visualize_line_by_line(
            two_stocks_df_dif,
            f"arbitrage_two_stocks_diff_{pair.replace('/','_')}_{timeframe}_{limit}",
            highlite_zero_x=True,
        )
        visualize_line_by_line(
            two_stocks_df,
            f"arbitrage_two_stocks_diff_percent_{pair.replace('/','_')}_{timeframe}_{limit}",
            highlite_zero_x=True,
        )
        # break


def get_pairs_list(stock_names):
    import ccxt

    logger = mp_logging.LoggerWorker().getLogger(__name__)
    logger.info("start 'get_pairs_list'")

    pairs_USDT = {}
    all_pairs = set()
    for stock_name in stock_names:
        ex = getattr(ccxt, stock_name)()

        pairs_USDT[stock_name] = []
        for market in ex.fetch_markets():
            if market["spot"] and market["type"] == "spot":
                symbol = market["symbol"]
                if "/" not in symbol:
                    continue
                if "USDC" in symbol:
                    continue
                if "USDT" in symbol:
                    pairs_USDT[stock_name].append(symbol)
                    all_pairs.add(symbol)

    pairs_USDT_everywhere = []
    for pair in all_pairs:
        is_exist = True
        for stock_name in stock_names:
            if pair not in pairs_USDT[stock_name]:
                is_exist = False
                break
        if is_exist:
            pairs_USDT_everywhere.append(pair)

    return pairs_USDT_everywhere


def main():
    logger_listener = mp_logging.LoggerListener()
    logging_queue = logger_listener.start_listener_process(log_file_path="arbitrage_pair_wings.log")
    logger = mp_logging.LoggerWorker().getLogger(__name__)
    logger.info("start")

    stop_event = mp.Event()

    timeframe = "1m"
    limit = 60

    stock_names = {"binance", "bybit", "htx", "mexc", "kucoin"}  # "okx"

    pairs = [
        "ETH/USDT",
        "BCH/USDT",
    ]

    pairs = get_pairs_list(stock_names)

    logger.info(f"found {len(pairs)} pairs")
    logger.info(pairs)

    p_data = ohlcv(
        stock_names=stock_names,
        pairs=pairs,
        timeframe=timeframe,
        limit=limit,
        stop_event=stop_event,
        logging_queue=logging_queue,
    )

    # find_best_stocks_pair(stock_names, pairs, timeframe, limit, p_data)

    stop_event.set()
    logger_listener.stop_listener_process()


if __name__ == "__main__":
    main()

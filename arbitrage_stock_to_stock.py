"""
arbitrage between stocks
"""

import os

import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import itertools
import math
import shutil
import time
import json5
import multiprocessing as mp
from multiprocessing.sharedctypes import Array
import concurrent.futures

from pypdf import PdfWriter

import mp_logging


def visualize_line_by_line(data_dict, file_name, dir_results_name, label=None, logging_queue=None):
    """
    data_dict: {pair: df}  - pairs data to show
    """
    if logging_queue:
        mp_logging.LoggerWorker().logger_worker_configure(logging_queue)
    logger = mp_logging.LoggerWorker().getLogger(__name__)

    if label:
        logger.info(label + " START")

    pairs_all = list(data_dict.keys())

    xticks_num = 1

    files = []
    for i, pair in enumerate(pairs_all):

        columns_plot = {
            "price": [x for x in data_dict[pair].columns.tolist() if "_CLOSE" in x],
            "diff": [x for x in data_dict[pair].columns.tolist() if "_DIFF" in x],
            "profit": [x for x in data_dict[pair].columns.tolist() if "_PROFIT" in x],
            "volume": [x for x in data_dict[pair].columns.tolist() if "_VOLUME" in x],
        }

        n_z = sum([bool(columns_plot[x]) for x in columns_plot.keys()])
        # (rows, columns)
        layout = [n_z, 1]
        fig, _axes = plt.subplots(nrows=layout[0], ncols=layout[1], sharex=True)
        fig.set_size_inches(w=2000 / 100, h=layout[0] * 350 / 100)
        fig.subplots_adjust(hspace=0)
        if isinstance(_axes, np.ndarray):
            axe = _axes.ravel()
        else:
            axe = [_axes]
        axes = {}
        j = 0
        for x in columns_plot.keys():
            if columns_plot[x]:
                axes[x] = axe[j]
                j += 1

        # plot PRICES ==============================================================================================
        if columns_plot["price"]:
            axes["price"].set_xticklabels([])
            axes["price"].tick_params(left=False, bottom=False)

            axes["price"].set_xticks(np.arange(0, data_dict[pair].size, xticks_num))
            axes["price"].set_title(pair + " prices")

            try:
                data_dict[pair].plot(y=columns_plot["price"], kind="line", ax=axes["price"], grid=True)
            except Exception as err:
                logger.error(
                    f"plot PRICES {pair}: data_dict[pair].columns: "
                    f"{data_dict[pair].columns.tolist()}, data_dict_price_volume[pair].columns: "
                    f"error: {str(err)}"
                )

        # plot PRICES diff =========================================================================================
        if columns_plot["diff"]:
            axes["diff"].set_xticklabels([])
            axes["diff"].tick_params(left=False, bottom=False)

            axes["diff"].set_xticks(np.arange(0, data_dict[pair].size, xticks_num))
            axes["diff"].set_title(pair + " % diff")
            axes["diff"].axhline(0, color="black", linewidth=2)

            try:
                data_dict[pair].plot(y=columns_plot["diff"], kind="line", ax=axes["diff"], grid=True)
            except Exception as err:
                logger.error(
                    f"plot PRICES diff {pair}: no numeric data to plot data_dict[pair].columns: "
                    f"{data_dict[pair].columns.tolist()}, data_dict_price_volume[pair].columns: "
                    f"error: {str(err)}"
                )

        # plot PROFIT ==============================================================================================
        if columns_plot["profit"]:
            axes["profit"].set_xticklabels([])
            axes["profit"].tick_params(left=False, bottom=False)

            axes["profit"].set_xticks(np.arange(0, data_dict[pair].size, xticks_num))
            axes["profit"].set_title(pair + " profit. independent arbitrage trade 100 USDT each time. no fees included")
            axes["profit"].axhline(0, color="black", linewidth=2)

            try:
                data_dict[pair].plot(y=columns_plot["profit"], kind="line", ax=axes["profit"], grid=True)
            except Exception as err:
                logger.error(
                    f"plot PROFIT {pair}: no numeric data to plot data_dict[pair].columns: "
                    f"{data_dict[pair].columns.tolist()}, data_dict_price_volume[pair].columns: "
                    f"error: {str(err)}"
                )

        # plot VOLUMES ============================================================================================
        if columns_plot["volume"]:
            axes["volume"].set_xticklabels(np.arange(0, data_dict[pair].size, xticks_num))
            axes["volume"].tick_params(left=False, bottom=True)

            axes["volume"].set_yscale("log")

            axes["volume"].set_xticks(np.arange(0, data_dict[pair].size, xticks_num))
            axes["volume"].set_title(pair + " volumes")

            try:
                data_dict[pair].plot(y=columns_plot["volume"], kind="line", ax=axes["volume"], grid=True, linewidth=3)
            except Exception as err:
                logger.error(
                    f"plot VOLUMES {pair}: no numeric data to plot data_dict[pair].columns: "
                    f"{data_dict[pair].columns.tolist()}, data_dict_price_volume[pair].columns: "
                    f"error: {str(err)}"
                )
            d = data_dict[pair].index
            for column in columns_plot["volume"]:
                axes["volume"].fill_between(
                    d,
                    data_dict[pair][column],
                    alpha=0.2,
                    interpolate=True,
                )

        # save ====================================================================================================
        fig.tight_layout()
        files.append(os.path.join(dir_results_name, f"{file_name}_{i+1}_{len(pairs_all)}.pdf"))
        fig.savefig(files[-1], bbox_inches="tight")
        plt.close(fig)

    # combine all files into one
    if files and os.path.exists(f"{file_name}.pdf"):
        os.remove(f"{file_name}.pdf")
    if len(files) > 1:
        merger = PdfWriter()
        for pdf in files:
            merger.append(pdf)
        merger.write(os.path.join(dir_results_name, f"{file_name}.pdf"))
        merger.close()
        for file in files:
            os.remove(file)
    elif len(files) == 1:
        os.rename(files[0], os.path.join(dir_results_name, f"{file_name}.pdf"))

    if label:
        logger.info(label + " END")


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

            except Exception as err:
                logger.error(f"error on {stock_name}: {data['pair']}  error: {str(err)}")
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
        request.value = bytes(d, "utf-8")
        stock_names_check = stock_names.copy()
        big_df = pd.DataFrame()
        while stock_names_check:
            stock_name, ohlcv, t = response.get(block=True)
            if ohlcv:
                df = pd.DataFrame(ohlcv, columns=["TIME", "OPEN", "HIGH", "LOW", "CLOSE", "VOLUME"]).drop(
                    "TIME", axis=1
                )
                # df["TIME"] = pd.to_datetime(df["TIME"], unit="ms")

                # df.set_index("TIME")
                big_df[stock_name + "_CLOSE"] = df["CLOSE"]
                big_df[stock_name + "_VOLUME"] = df["VOLUME"]
            stock_names_check.remove(stock_name)
        big_df = big_df[sorted(big_df.columns.tolist())]

        return big_df

    p_data = {}
    for i, pair in enumerate(pairs):
        logger.info(f"collecting {i+1} of {len(pairs)}: {pair}")
        p_data[pair] = get_ohlcv(pair)

    return p_data


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


def calc_best_stock_exchange_pairs(
    stock_combs, p_data, timeframe, limit, dir_results_name, plot=True, logging_queue=None
):
    """
    Calculate (and plot) the best stock exchange pairs to use for arbitrage
    Plot charts for all pairs of `p_data`:
        - Prices from two stocks
        - Prices difference in % (stock A - stock B)
        - Profit from arbitrage based on 100 USDT trade each time. Fees are not included. Volume is taken into account
        - Volumes from two stocks
    """

    def calc_price_diff_percent(p_data, base_A_stock, stock_B):
        logger = mp_logging.LoggerWorker().getLogger(__name__)
        p_data_dif_percent = {}
        pairs = list(p_data.keys())
        base_column = f"{base_A_stock}_CLOSE"
        column = f"{stock_B}_CLOSE"
        for i, pair in enumerate(pairs):
            df_percent = pd.DataFrame()
            try:
                df_percent[base_A_stock + "_DIFF"] = p_data[pair][base_column] - p_data[pair][base_column]
                df_percent[stock_B + "_DIFF"] = (
                    (p_data[pair][column] - p_data[pair][base_column]) / p_data[pair][column]
                ) * 100
            except Exception as err:
                logger.error(f"calc_price_diff_percent: {base_A_stock}, {stock_B}, {pair}, err: {err}")
                continue

            p_data_dif_percent[pair] = df_percent
        return p_data_dif_percent

    def calc_arbitrage(stock_name_A_base, stock_name_B, p_data, start_USDT_amount):
        def for_one_moment(df: pd.Series):
            """
            start_USDT_amount: amount for trading. EACH TRADE the same amount!

            return: sorted by non zero profit
            """

            try:
                price_A_base = df[f"{stock_name_A_base}_CLOSE"]
                volume_A_base = df[f"{stock_name_A_base}_VOLUME"]
                price_B = df[f"{stock_name_B}_CLOSE"]
                volume_B = df[f"{stock_name_B}_VOLUME"]
            except:
                return 0

            def check_volume(ac):
                treshold = 10 * ac  # do arbitrage only if the volume is big enough on stocks
                if treshold < volume_B and treshold < volume_A_base:
                    return True
                else:
                    return False

            diff = (price_A_base - price_B) / price_A_base
            if diff > 0:
                # cheap is B
                amount_coins = start_USDT_amount / price_B
                profit = (amount_coins * price_A_base) - start_USDT_amount
            elif diff < 0:
                # cheap is A
                amount_coins = start_USDT_amount / price_A_base
                profit = (amount_coins * price_B) - start_USDT_amount
            else:
                amount_coins = 0
                profit = 0

            # check if enough volume on stocks
            if not check_volume(amount_coins):
                profit = 0
            return profit

        pairs = list(p_data.keys())
        p_data_profit = {}
        pair_non_zero_profits = []
        for pair in pairs:
            p_data_profit[pair] = p_data[pair].apply(for_one_moment, axis=1)
            score = p_data_profit[pair].astype(bool).sum()
            pair_non_zero_profits.append((pair, score))
        pair_non_zero_profits.sort(key=lambda x: x[1], reverse=True)

        # sort by total profit
        p_data_profit_out = {}
        for pair, _ in pair_non_zero_profits:
            p_data_profit_out[pair] = p_data_profit[pair]

        return p_data_profit_out, pair_non_zero_profits

    logger = mp_logging.LoggerWorker().getLogger(__name__)
    sn1_sn2_weighted = []
    for i, (sn1, sn2) in enumerate(stock_combs):
        logger.info(f"calculating for stocks {i+1} of {len(stock_combs)}: {sn1} {sn2}")
        logger.info(f"\tcalc_price_diff_percent ...")
        p_data_dif_percent = calc_price_diff_percent(p_data, base_A_stock=sn1, stock_B=sn2)

        logger.info(f"\tcalc_arbitrage ...")
        p_data_profit, pair_non_zero_profits = calc_arbitrage(
            stock_name_A_base=sn1, stock_name_B=sn2, p_data=p_data, start_USDT_amount=100
        )

        # sorted by profit
        p_data_for_plot = {}
        pp = []
        for pair, pair_non_zero_profit in pair_non_zero_profits:
            if (pair not in p_data_dif_percent) or (pair not in p_data_profit) or (pair not in p_data):
                continue
            pp.append(pair_non_zero_profit)
            df = pd.DataFrame()  # otherwise I have last anf first points connected.. idk why
            df[f"{sn1}_{sn2}_PROFIT"] = p_data_profit[pair]
            p_data_for_plot[pair] = pd.concat([p_data[pair], p_data_dif_percent[pair], df])

        # average non zero profit
        avg_profit = sum(pp) / len(pp)

        sn1_sn2_weighted.append(((sn1, sn2), p_data_for_plot, avg_profit))
    logger.info(f"Stocks pairs best to trade (from best to worse):")
    stocks_ranked = sorted(sn1_sn2_weighted, key=lambda x: x[2], reverse=True)
    for rank, ((sn1, sn2), p_data_for_plot, avg_profit) in enumerate(stocks_ranked):
        logger.info(f"\t {rank+1}: {sn1} {sn2}")

    if plot:
        logger.info("")
        with concurrent.futures.ProcessPoolExecutor(max_workers=os.cpu_count()) as executor:
            for rank, ((sn1, sn2), p_data_for_plot, avg_profit) in enumerate(stocks_ranked):

                # drop columns not related to sn1, sn2
                _pp = {}
                for pair in p_data_for_plot.keys():
                    _pp[pair] = p_data_for_plot[pair].copy(deep=True)
                    cols = [x for x in _pp[pair].columns.tolist() if not x.startswith(sn1) and not x.startswith(sn2)]
                    _pp[pair] = _pp[pair].drop(cols, axis=1)

                future = executor.submit(
                    visualize_line_by_line,
                    **{
                        "data_dict": _pp,
                        "dir_results_name": dir_results_name,
                        "file_name": f"00{rank+1}_arbitrage_{sn1}_{sn2}_{timeframe}_{limit}",
                        "label": f"\t\tplotting for stocks {sn1} {sn2} ({rank+1} of {len(stock_combs)})",
                        "logging_queue": logging_queue,
                    },
                )

    return stocks_ranked


def main():
    logger_listener = mp_logging.LoggerListener()
    logging_queue = mp.Manager().Queue()
    logger_listener.start_listener_process(queue=logging_queue, log_file_path="arbitrage_stock_to_stock.log")
    logger = mp_logging.LoggerWorker().getLogger(__name__)
    logger.info("start")

    dir_results_name = "arb_stock_to_stock_results"
    if not os.path.exists(dir_results_name):
        os.mkdir(dir_results_name)
    else:
        shutil.rmtree(dir_results_name)
        os.mkdir(dir_results_name)

    stop_event = mp.Event()

    timeframe = "1m"
    limit = 60

    stock_names = {"binance", "bybit", "htx", "mexc", "kucoin", "okx"}

    stock_combs = list(itertools.combinations(stock_names, 2))

    logger.info(f"timeframe: {timeframe}")
    logger.info(f"limit: {limit}")
    logger.info(f"stock_names: {stock_names}")
    logger.info(f"stock combinations: {len(stock_combs)} pairs")

    pairs = [
        "ETH/USDT",
        "BCH/USDT",
        "AAVE/USDT",
    ]

    pairs = get_pairs_list(stock_names)

    logger.info(f"found {len(pairs)} crypto pairs: {pairs}")

    p_data = ohlcv(
        stock_names=stock_names,
        pairs=pairs,
        timeframe=timeframe,
        limit=limit,
        stop_event=stop_event,
        logging_queue=logging_queue,
    )

    stop_event.set()

    logger.info(f"plotting raw pairs data ...")
    visualize_line_by_line(
        p_data,
        dir_results_name=dir_results_name,
        file_name=f"arbitrage_raw_{timeframe}_{limit}",
    )

    stocks_ranked = calc_best_stock_exchange_pairs(
        stock_combs, p_data, timeframe, limit, dir_results_name, plot=True, logging_queue=logging_queue
    )

    stop_event.set()
    logger_listener.stop_listener_process()


if __name__ == "__main__":
    main()

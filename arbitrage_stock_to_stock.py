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

from pypdf import PdfWriter

import mp_logging


def visualize_line_by_line(data_dict, file_name, data_dict_helped, dir_results_name):
    """
    data_dict: {pair: df}  - pairs data to show. for example diffs. Columns "{stock_name}_CLOSE", optional: "{stock_name}_VOLUME"
    data_dict_helped: {pair: df}  - pairs data to help, raw prices and volume. Columns "{stock_name}_CLOSE", "{stock_name}_VOLUME"
    """
    logger = mp_logging.LoggerWorker().getLogger(__name__)

    pairs_all = list(data_dict.keys())

    xticks_num = 1

    files = []
    for i, pair in enumerate(pairs_all):

        # (rows, columns)
        layout = [4, 1]

        fig, axes = plt.subplots(nrows=layout[0], ncols=layout[1], sharex=True)
        fig.set_size_inches(w=2000 / 100, h=layout[0] * 350 / 100)
        fig.subplots_adjust(hspace=0)
        if isinstance(axes, np.ndarray):
            axe = axes.ravel()
        else:
            axe = [axes]

        ax_price = axe[0]
        ax_price_diff = axe[1]
        ax_price_profit = axe[2]
        ax_volume = axe[3]

        # plot PRICES ==============================================================================================
        ax_price.set_xticklabels([])
        ax_price.tick_params(left=False, bottom=False)

        ax_price.set_xticks(np.arange(0, data_dict[pair].size, xticks_num))
        ax_price.set_title(pair)

        price_cols = [x for x in data_dict[pair].columns.tolist() if "_CLOSE" in x]
        try:
            data_dict_helped[pair].plot(y=price_cols, kind="line", ax=ax_price, grid=True)
        except Exception as err:
            logger.error(
                f"plot PRICES {pair}: data_dict[pair].columns: "
                f"{data_dict[pair].columns.tolist()}, data_dict_helped[pair].columns: "
                f"{data_dict_helped[pair].columns.tolist()} error: {str(err)}"
            )

        # plot PRICES diff =========================================================================================
        ax_price_diff.set_xticklabels([])
        ax_price_diff.tick_params(left=False, bottom=False)

        ax_price_diff.set_xticks(np.arange(0, data_dict[pair].size, xticks_num))
        ax_price_diff.set_title(pair + " % diff")
        ax_price_diff.axhline(0, color="black", linewidth=2)

        price_cols_diff = [x for x in data_dict[pair].columns.tolist() if "_CLOSE" in x]
        try:
            data_dict[pair].plot(y=price_cols_diff, kind="line", ax=ax_price_diff, grid=True)
        except Exception as err:
            logger.error(
                f"plot PRICES diff {pair}: no numeric data to plot data_dict[pair].columns: "
                f"{data_dict[pair].columns.tolist()}, data_dict_helped[pair].columns: "
                f"{data_dict_helped[pair].columns.tolist()} error: {str(err)}"
            )

        # plot PROFIT ==============================================================================================
        ax_price_profit.set_xticklabels([])
        ax_price_profit.tick_params(left=False, bottom=False)

        ax_price_profit.set_xticks(np.arange(0, data_dict[pair].size, xticks_num))
        ax_price_profit.set_title(pair + " profit. independent arbitrage trade 100 USDT each time. no fees included")
        ax_price_profit.axhline(0, color="black", linewidth=2)

        price_cols_prof = [x for x in data_dict[pair].columns.tolist() if "_PROFIT" in x]
        try:
            data_dict[pair].plot(y=price_cols_prof, kind="line", ax=ax_price_profit, grid=True)
        except Exception as err:
            logger.error(
                f"plot PROFIT {pair}: no numeric data to plot data_dict[pair].columns: "
                f"{data_dict[pair].columns.tolist()}, data_dict_helped[pair].columns: "
                f"{data_dict_helped[pair].columns.tolist()} error: {str(err)}"
            )

        # plot VOLUMES ============================================================================================
        ax_volume.set_xticklabels([])
        ax_volume.tick_params(left=False, bottom=False)

        ax_volume.set_yscale("log")

        ax_volume.set_xticks(np.arange(0, data_dict_helped[pair].size, xticks_num))
        ax_volume.set_title(pair + " VOLUMES")

        price_vols = [x for x in data_dict[pair].columns.tolist() if "_VOLUME" in x]
        try:
            data_dict_helped[pair].plot(y=price_vols, kind="line", ax=ax_volume, grid=True, linewidth=3)
        except Exception as err:
            logger.error(
                f"plot VOLUMES {pair}: no numeric data to plot data_dict[pair].columns: "
                f"{data_dict[pair].columns.tolist()}, data_dict_helped[pair].columns: "
                f"{data_dict_helped[pair].columns.tolist()} error: {str(err)}"
            )
        d = data_dict_helped[pair].index
        for column in price_vols:
            ax_volume.fill_between(
                d,
                data_dict_helped[pair][column],
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


def calc_best_stock_exchange_pairs(stock_combs, p_data, timeframe, limit, dir_results_name, plot=True):
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
        for i, pair in enumerate(pairs):
            df_percent = pd.DataFrame()
            base_column = f"{base_A_stock}_CLOSE"
            for column in p_data[pair].columns.tolist():
                if column.startswith(base_A_stock) or column.startswith(stock_B):
                    try:
                        if "VOLUME" not in column:
                            df_percent[column] = (
                                (p_data[pair][column] - p_data[pair][base_column]) / p_data[pair][column]
                            ) * 100
                        else:
                            df_percent[column] = p_data[pair][column]
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
            pp.append(pair_non_zero_profit)
            p_data_for_plot[pair] = p_data_dif_percent[pair]
            p_data_for_plot[pair][f"{sn1}_{sn2}_PROFIT"] = p_data_profit[pair]

        # average non zero profit
        avg_profit = sum(pp) / len(pp)

        sn1_sn2_weighted.append(((sn1, sn2), p_data_for_plot, avg_profit))
    logger.info(f"Stocks pairs best to trade (from best to worse):")
    stocks_ranked = sorted(sn1_sn2_weighted, key=lambda x: x[2], reverse=True)
    for rank, ((sn1, sn2), p_data_for_plot, avg_profit) in enumerate(stocks_ranked):
        logger.info(f"\t {rank+1}: {sn1} {sn2}")

    if plot:
        logger.info("")
        for rank, ((sn1, sn2), p_data_for_plot, avg_profit) in enumerate(stocks_ranked):
            logger.info(f"\t\tplotting for stocks {sn1} {sn2} ({rank+1} of {len(stock_combs)}) ...")
            visualize_line_by_line(
                p_data_for_plot,
                data_dict_helped=p_data,
                dir_results_name=dir_results_name,
                file_name=f"00{rank+1}_arbitrage_{sn1}_{sn2}_{timeframe}_{limit}",
            )

    return stocks_ranked


def main():
    logger_listener = mp_logging.LoggerListener()
    logging_queue = logger_listener.start_listener_process(log_file_path="arbitrage_pair_wings.log")
    logger = mp_logging.LoggerWorker().getLogger(__name__)
    logger.info("start")

    dir_results_name = "arb_pair_wings_results"
    if not os.path.exists(dir_results_name):
        os.mkdir(dir_results_name)
    else:
        shutil.rmtree(dir_results_name)
        os.mkdir(dir_results_name)

    stop_event = mp.Event()

    timeframe = "1m"
    limit = 60

    stock_names = {"binance", "bybit", "htx", "mexc", "kucoin"}  # "okx"

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

    stocks_ranked = calc_best_stock_exchange_pairs(stock_combs, p_data, timeframe, limit, dir_results_name, plot=True)

    stop_event.set()
    logger_listener.stop_listener_process()


if __name__ == "__main__":
    main()

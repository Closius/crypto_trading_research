"""
under construction...

arbitrage between pairs in one stock. triangular arbitrage
"""

import os
import ccxt
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import shutil
import math
import time
import json5
from pypdf import PdfWriter

import mp_logging

import sequence_calculator


def visualize_line_by_line(data_dict, file_name, dir_results_name, label=None, logging_queue=None):
    """
    data_dict: {sequence: df}  - seq data to show
    """
    if logging_queue:
        mp_logging.LoggerWorker().logger_worker_configure(logging_queue)
    logger = mp_logging.LoggerWorker().getLogger(__name__)

    if label:
        logger.info(label + " START")

    pairs_all = list(data_dict.keys())

    xticks_num = 1
    files = []
    for i, seq in enumerate(pairs_all):

        x_tickss = np.arange(0, data_dict[seq].shape[0], xticks_num)

        columns_plot = {
            "price_beg": [x for x in data_dict[seq].columns.tolist() if "_beg_CLOSE" in x],
            "price_mid": [x for x in data_dict[seq].columns.tolist() if "_mid_CLOSE" in x],
            "price_end": [x for x in data_dict[seq].columns.tolist() if "_end_CLOSE" in x],
            "profit": [x for x in data_dict[seq].columns.tolist() if "profit" in x],
            "volume": [x for x in data_dict[seq].columns.tolist() if "_VOLUME" in x],
        }

        price_beg = columns_plot["price_beg"][0].split("_")[0]
        price_mid = columns_plot["price_mid"][0].split("_")[0]
        price_end = columns_plot["price_end"][0].split("_")[0]

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

        # plot PRICES first pair ==============================================================================================
        if columns_plot["price_beg"]:
            axes["price_beg"].set_xticklabels([])
            axes["price_beg"].tick_params(left=False, bottom=False)

            axes["price_beg"].set_xticks(x_tickss)
            axes["price_beg"].set_title(str(seq) + "          " + price_beg + " price begin")

            try:
                data_dict[seq].plot(y=columns_plot["price_beg"], kind="line", ax=axes["price_beg"], grid=True)
            except Exception as err:
                logger.error(
                    f"plot PRICES begin {seq}: data_dict[pair].columns: "
                    f"{data_dict[seq].columns.tolist()}, data_dict_price_volume[pair].columns: "
                    f"error: {str(err)}"
                )

        # plot PRICES middle pair =========================================================================================
        if columns_plot["price_mid"]:
            axes["price_mid"].set_xticklabels([])
            axes["price_mid"].tick_params(left=False, bottom=False)

            axes["price_mid"].set_xticks(x_tickss)
            axes["price_mid"].set_title(price_mid + " price middle")

            try:
                data_dict[seq].plot(y=columns_plot["price_mid"], kind="line", ax=axes["price_mid"], grid=True)
            except Exception as err:
                logger.error(
                    f"plot PRICES middle {seq}: no numeric data to plot data_dict[pair].columns: "
                    f"{data_dict[seq].columns.tolist()}, data_dict_price_volume[pair].columns: "
                    f"error: {str(err)}"
                )

        # plot PRICES last pair ==============================================================================================
        if columns_plot["price_end"]:
            axes["price_end"].set_xticklabels([])
            axes["price_end"].tick_params(left=False, bottom=False)

            axes["price_end"].set_xticks(x_tickss)
            axes["price_end"].set_title(price_end + " price end")

            try:
                data_dict[seq].plot(y=columns_plot["price_end"], kind="line", ax=axes["price_end"], grid=True)
            except Exception as err:
                logger.error(
                    f"plot PRICES end {seq}: no numeric data to plot data_dict[pair].columns: "
                    f"{data_dict[seq].columns.tolist()}, data_dict_price_volume[pair].columns: "
                    f"error: {str(err)}"
                )

        # plot PROFIT ==============================================================================================
        if columns_plot["profit"]:

            axes["profit"].set_xticklabels([])
            axes["profit"].tick_params(left=False, bottom=False)

            axes["profit"].set_xticks(x_tickss)
            axes["profit"].set_title("profit")
            axes["profit"].axhline(0, color="black", linewidth=2)

            try:
                data_dict[seq].plot(y=columns_plot["profit"], kind="line", ax=axes["profit"], grid=True)
            except Exception as err:
                logger.error(
                    f"plot PROFIT {seq}: no numeric data to plot data_dict[pair].columns: "
                    f"{data_dict[seq].columns.tolist()}, data_dict_price_volume[pair].columns: "
                    f"error: {str(err)}"
                )

            # annotate with last price
            pft = data_dict[seq]["profit"].to_list()
            for x, lbl in enumerate(data_dict[seq]["pft_label"].to_list()):
                axes["profit"].annotate(lbl, (x, pft[x]))

        # plot VOLUMES ============================================================================================
        if columns_plot["volume"]:
            axes["volume"].set_xticklabels(x_tickss)
            axes["volume"].tick_params(left=False, bottom=True)

            axes["volume"].set_yscale("log")

            axes["volume"].set_xticks(x_tickss)
            axes["volume"].set_title(str(seq) + " volumes")

            try:
                data_dict[seq].plot(y=columns_plot["volume"], kind="line", ax=axes["volume"], grid=True, linewidth=3)
            except Exception as err:
                logger.error(
                    f"plot VOLUMES {seq}: no numeric data to plot data_dict[pair].columns: "
                    f"{data_dict[seq].columns.tolist()}, data_dict_price_volume[pair].columns: "
                    f"error: {str(err)}"
                )
            d = data_dict[seq].index
            for column in columns_plot["volume"]:
                axes["volume"].fill_between(
                    d,
                    data_dict[seq][column],
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


def get_pairs_no_USDT_spot(exchange):

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


def get_ohlcv(exchange, pair, timeframe, limit) -> pd.DataFrame | None:
    logger = mp_logging.LoggerWorker().getLogger(__name__)
    if timeframe[-1] != "m":
        raise ValueError('timeframe[-1] != "m"')
    tf_milliseconds = int(timeframe[:-1]) * 60000
    # since = exchange.milliseconds () - 86400000  # -1 day from now
    since = exchange.milliseconds() - (tf_milliseconds * limit)
    try:
        ohlcv = exchange.fetch_ohlcv(pair, timeframe, since=since, limit=limit)
    except Exception as err:
        logger.error(f"error: {pair}  error: {str(err)}")
        ohlcv = []

    if ohlcv:
        big_df = pd.DataFrame()
        df = pd.DataFrame(ohlcv, columns=["TIME", "OPEN", "HIGH", "LOW", "CLOSE", "VOLUME"]).drop("TIME", axis=1)
        # df["TIME"] = pd.to_datetime(df["TIME"], unit="ms")
        # df.set_index("TIME")
        big_df[pair + "_CLOSE"] = df["CLOSE"]
        big_df[pair + "_VOLUME"] = df["VOLUME"]

        return big_df


def calc_arbitrage(s_data, init_invest):
    logger = mp_logging.LoggerWorker().getLogger(__name__)

    def for_one_moment(df: pd.Series):
        """
        start_USDT_amount: amount for trading. EACH TRADE the same amount!

        return: sorted by non zero profit
        """

        def perform_triangular_arbitrage(
            prc1,
            prc2,
            prc3,
            vol1,
            vol2,
            vol3,
            initial_investment,
            transaction_fee,
            min_profit,
        ):

            def check_volume(ammount, volume):
                treshold = 10 * ammount  # do arbitrage only if the volume is big enough on stocks
                if treshold < volume:
                    return True
                else:
                    return False

            def check_buy_buy_sell(p1, p2, p3, v1, v2, v3):
                buy_quantity1 = (initial_investment / p1) if side_forward[0] == "buy" else (initial_investment * p1)
                v1_check = buy_quantity1 if side_forward[0] == "buy" else initial_investment

                buy_quantity2 = (buy_quantity1 / p2) if side_forward[1] == "buy" else (buy_quantity1 * p2)
                v2_check = buy_quantity2 if side_forward[1] == "buy" else buy_quantity1

                final_price = (buy_quantity2 * p3) if side_forward[2] == "sell" else (buy_quantity2 / p3)
                v3_check = final_price if side_forward[2] == "buy" else buy_quantity2
                if not check_volume(v1_check, v1) or not check_volume(v2_check, v2) or not check_volume(v3_check, v3):
                    return 0, "bv"
                else:
                    return final_price, "b"

            def check_buy_sell_sell(p1, p2, p3, v1, v2, v3):
                buy_quantity1 = (initial_investment / p1) if side_backward[0] == "buy" else (initial_investment * p1)
                v1_check = buy_quantity1 if side_backward[0] == "buy" else initial_investment

                sell_price2 = (buy_quantity1 * p2) if side_backward[1] == "sell" else (buy_quantity1 / p2)
                v2_check = sell_price2 if side_backward[1] == "buy" else buy_quantity1

                final_price = (sell_price2 * p3) if side_backward[2] == "sell" else (sell_price2 / p3)
                v3_check = final_price if side_backward[2] == "buy" else sell_price2
                if not check_volume(v1_check, v1) or not check_volume(v2_check, v2) or not check_volume(v3_check, v3):
                    # logger.info("check_buy_sell_sell volume")
                    return 0, "sv"
                else:
                    return final_price, "s"

            def check_profit_loss(total_price_after_sell):
                apprx_brokerage = transaction_fee * initial_investment / 100 * 3
                min_profitable_price = initial_investment + apprx_brokerage + min_profit
                profit_loss = total_price_after_sell - min_profitable_price
                return profit_loss

            final_price, t = check_buy_buy_sell(prc1, prc2, prc3, vol1, vol2, vol3)
            profit = check_profit_loss(final_price)
            if profit > 0:
                return profit, t

            final_price, t = check_buy_sell_sell(prc3, prc2, prc1, vol3, vol2, vol1)
            profit = check_profit_loss(final_price)
            if profit > 0:
                return profit, t

            # logger.info("0 profit.. ")
            return 0, "n"

        p_beg = None
        p_mid = None
        p_end = None
        v_beg = None
        v_mid = None
        v_end = None

        # print(f"======================================")

        for index, value in df.items():
            # print(index, value)
            if "_beg_CLOSE" in index:
                p_beg = value
            elif "_mid_CLOSE" in index:
                p_mid = value
            elif "_end_CLOSE" in index:
                p_end = value
            elif "_beg_VOLUME" in index:
                v_beg = value
            elif "_mid_VOLUME" in index:
                v_mid = value
            elif "_end_VOLUME" in index:
                v_end = value
            else:
                logger.error(f"wrong index: {index}")
                return pd.Series([0, "i"], index=["profit", "pft_label"])

        # print(f"p_beg: {p_beg}")
        # print(f"p_mid: {p_mid}")
        # print(f"p_end: {p_end}")
        # print(f"v_beg: {v_beg}")
        # print(f"v_mid: {v_mid}")
        # print(f"v_end: {v_end}")

        if np.isnan(p_beg) or np.isnan(p_mid) or np.isnan(p_end):
            # logger.info("shit price data")
            return pd.Series([0, "p"], index=["profit", "pft_label"])
        if np.isnan(v_beg) or np.isnan(v_mid) or np.isnan(v_end):
            # logger.info("shit volume data")
            return pd.Series([0, "v"], index=["profit", "pft_label"])

        res = perform_triangular_arbitrage(
            p_beg,
            p_mid,
            p_end,
            v_beg,
            v_mid,
            v_end,
            init_invest,
            transaction_fee=0,
            min_profit=0,
        )
        return pd.Series(res, index=["profit", "pft_label"])

    def check_side(s):
        _s = [x.split("/") for x in s]

        # forward
        op1 = "buy" if _s[0][1] == "USDT" else "sell"
        base1 = _s[0][1] if _s[0][1] != "USDT" else _s[0][0]
        op2 = "buy" if _s[1][1] == base1 else "sell"
        op3 = "sell" if _s[2][1] == "USDT" else "buy"

        fw = (op1, op2, op3)

        # backward
        op1 = "buy" if _s[2][1] == "USDT" else "sell"
        base1 = _s[2][1] if _s[2][1] != "USDT" else _s[2][0]
        op2 = "buy" if _s[1][1] == base1 else "sell"
        op3 = "sell" if _s[0][1] == "USDT" else "buy"

        bw = (op1, op2, op3)

        return fw, bw

    seqs = list(s_data.keys())
    s_data_profit = {}
    seqs_non_zero_profits = []
    for seq in seqs:
        side_forward, side_backward = check_side(seq)
        s_data_profit[seq] = s_data[seq].apply(for_one_moment, axis=1)
        score = s_data_profit[seq]["profit"].astype(bool).sum()
        seqs_non_zero_profits.append((seq, score))
    seqs_non_zero_profits.sort(key=lambda x: x[1], reverse=True)

    # sort by total profit
    s_data_profit_out = {}
    for seq, _score in seqs_non_zero_profits:
        if _score > 0:
            s_data_profit_out[seq] = pd.concat([s_data[seq], s_data_profit[seq]], axis=1)

    logger.info(f"Sequences best to trade (from best to worse) seq, score non zero profit trades:")
    for rank, (seq, score) in enumerate(seqs_non_zero_profits):
        logger.info(f"\t {rank+1}: {seq} {score}")

    logger.info(
        """
    legend for Profit graph:
        "bv" - buy_buy_sell - not enough volume
        "b" - buy_buy_sell - profit
    
        "sv" - buy_sell_sell - not enough volume
        "s" - buy_sell_sell - profit
    
        "n" - no profit by both buy_buy_sell and buy_sell_sell
        
        "i" - wrong index
        "p" - wrong price
        "v" - wrong volume
    """
    )

    return s_data_profit_out, seqs_non_zero_profits


def main():
    logger_listener = mp_logging.LoggerListener()
    logging_queue = logger_listener.start_listener_process(log_file_path="arbitrage_triangular.log")
    logger = mp_logging.LoggerWorker().getLogger(__name__)
    logger.info("start")

    dir_results_name = "arb_triangular_results"
    if not os.path.exists(dir_results_name):
        os.mkdir(dir_results_name)
    else:
        shutil.rmtree(dir_results_name)
        os.mkdir(dir_results_name)

    stock_name = "binance"
    exchange = getattr(ccxt, stock_name)()

    timeframe = "1m"
    limit = 60

    logger.info(f"timeframe: {timeframe}")
    logger.info(f"limit: {limit}")

    logger.info(f"stock_name: {stock_name}")
    pairs_USDT, pairs_no_USDT = get_pairs_no_USDT_spot(exchange)
    logger.info(f"pairs_USDT size: {len(pairs_USDT)}")
    logger.info(f"pairs_no_USDT size: {len(pairs_no_USDT)}")

    # sequences, uniq_pairs = sequence_calculator.sequence_calculator(
    #     pairs_no_USDT, start_coin="BTC", end_coin="TRUMP", max_depth=2
    # )

    sequences, uniq_pairs = sequence_calculator.simple_USDT_PAIR_USDT_sequence(pairs_USDT, pairs_no_USDT, first_n=500)

    # logger_listener.stop_listener_process()
    # return

    p_data = {}
    ranked_volume_pairs = []
    for i, pair in enumerate(uniq_pairs):
        logger.info(f"\tgetting pair data ({i+1} of {len(uniq_pairs)}) : {pair}")
        p_data[pair] = get_ohlcv(exchange, pair, timeframe, limit)
        if p_data[pair] is None:
            logger.info("\t\t\tno data")
            continue
        score = p_data[pair][pair + "_VOLUME"].astype(bool).sum()
        ranked_volume_pairs.append((pair, score))
    ranked_volume_pairs.sort(key=lambda x: x[1], reverse=True)

    logger.info("rank pairs by non zero volume: ")
    volume_ranked_sequences = []
    for pair, score in ranked_volume_pairs:
        logger.info(f"\t\t{pair}: {score}")
        for seq in sequences:
            if pair == seq[1]:
                volume_ranked_sequences.append(seq)

    logger.info(f"generate seq data")
    s_data = {}
    labels = ["beg", "mid", "end"]
    for n, seq in enumerate(volume_ranked_sequences):
        dfs = []
        for i, pair in enumerate(seq):
            if p_data[pair] is None:
                break
            dfs.append(p_data[pair].copy(deep=True))
            new_cols = {}
            for c in dfs[-1].columns.tolist():
                if c.endswith("VOLUME"):
                    new_cols[c] = c.replace("VOLUME", labels[i] + "_VOLUME")
                if c.endswith("CLOSE"):
                    new_cols[c] = c.replace("CLOSE", labels[i] + "_CLOSE")
            dfs[-1].rename(columns=new_cols, inplace=True)

        if len(dfs) == 3:
            s_data[seq] = pd.concat(dfs, axis=1)

    logger.info(f"calculate arbitrage")
    s_data_profit_out, seqs_non_zero_profits = calc_arbitrage(s_data, init_invest=100)

    # logger_listener.stop_listener_process()
    # return

    logger.info(f"visualise seq data")
    visualize_line_by_line(
        s_data_profit_out,
        dir_results_name=dir_results_name,
        file_name=f"arbitrage_tri_{timeframe}_{limit}",
    )

    logger_listener.stop_listener_process()


if __name__ == "__main__":
    main()

"""
arbitrage between pairs in one stock. arbitrage on correlations
"""

from dataclasses import dataclass
import itertools
import os
import ccxt
import json5
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import typing
import concurrent.futures

import mp_logging
import utils

import shutil


@dataclass
class PairsComb:
    pair1: str | None
    pair2: str | None
    properties: dict


def visualize_line_by_line(
    file_name: str,
    p_data: typing.Dict[str, pd.DataFrame],
    pair_combinations: typing.List[PairsComb] = None,
    label=None,
    logging_queue=None,
):
    """
    pair_combinations: list of dict
    """
    if logging_queue:
        mp_logging.LoggerWorker().logger_worker_configure(logging_queue)
    logger = mp_logging.LoggerWorker().getLogger(__name__)

    dir_results_name = os.path.dirname(file_name)

    if label:
        logger.info(label + " START")

    files = []
    for i, two_pairs in enumerate(pair_combinations):
        pair1 = two_pairs.pair1
        pair2 = two_pairs.pair2
        df = pd.DataFrame()
        if pair2:
            df = pd.concat([df, p_data[pair1]], axis=1).drop("AVERAGE", axis=1)
            df = pd.concat([df, p_data[pair2]], axis=1)
        else:
            df = p_data[pair1]
            pair1 = None

        columns_plot = {
            "price_1": [x for x in df.columns.tolist() if pair1 + "_CLOSE" in x] if pair1 else [],
            "price_2": [x for x in df.columns.tolist() if pair2 + "_CLOSE" in x] if pair2 else [],
            "prices_normalised": [x for x in df.columns.tolist() if "_NORM" in x],
            "profit": [x for x in df.columns.tolist() if "profit" in x],
            "diff_to_average": [x for x in df.columns.tolist() if "_DIFF_TO_AV" in x],
            "volume": [x for x in df.columns.tolist() if "_VOLUME" in x],
        }

        n_z = sum([bool(columns_plot[x]) for x in columns_plot.keys()])

        if n_z == 1:
            one_graph_height = 350 * 4
        else:
            one_graph_height = 350

        if df.shape[0] <= 250:
            xticks_num = 1
        else:
            xticks_num = 10
        x_tickss = np.arange(0, df.shape[0], xticks_num)

        fig, _axes = plt.subplots(nrows=n_z, ncols=1, sharex=True)
        fig.set_size_inches(w=2000 / 100, h=n_z * one_graph_height / 100)
        fig.subplots_adjust(hspace=0)
        fig.suptitle(json5.dumps(two_pairs.properties))
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

        # plot PRICES 1 pair ==============================================================================================
        if columns_plot["price_1"]:
            axes["price_1"].set_xticklabels([])
            axes["price_1"].tick_params(left=False, bottom=False)

            axes["price_1"].set_xticks(x_tickss)
            axes["price_1"].set_title(pair1)

            try:
                df.plot(y=columns_plot["price_1"], kind="line", ax=axes["price_1"], grid=True)
            except Exception as err:
                logger.error(f"plot {(pair1, pair2)} error: {str(err)}")

        # plot PRICES 2 pair =========================================================================================
        if columns_plot["price_2"]:
            axes["price_2"].set_xticklabels([])
            axes["price_2"].tick_params(left=False, bottom=False)

            axes["price_2"].set_xticks(x_tickss)
            axes["price_2"].set_title(pair2)

            try:
                df.plot(y=columns_plot["price_2"], kind="line", ax=axes["price_2"], grid=True)
            except Exception as err:
                logger.error(f"plot {(pair1, pair2)} error: {str(err)}")

        # plot PRICES normalized ==============================================================================================
        if columns_plot["prices_normalised"]:
            axes["prices_normalised"].set_xticklabels([])
            axes["prices_normalised"].tick_params(left=False, bottom=False)

            axes["prices_normalised"].set_xticks(x_tickss)
            axes["prices_normalised"].set_title("prices_normalised")

            try:
                df.plot(y=columns_plot["prices_normalised"], kind="line", ax=axes["prices_normalised"], grid=True)
            except Exception as err:
                logger.error(f"plot {(pair1, pair2)} error: {str(err)}")

            try:
                df.plot(y=["AVERAGE"], kind="line", ax=axes["prices_normalised"], grid=True, linewidth=3, color="black")
            except Exception as err:
                logger.error(f"plot {(pair1, pair2)} error: {str(err)}")

            if len(columns_plot["prices_normalised"]) > 100:
                axes["prices_normalised"].get_legend().remove()

        # plot DIFF to AVERAGE ============================================================================================
        if columns_plot["diff_to_average"]:
            axes["diff_to_average"].set_xticklabels(x_tickss)
            axes["diff_to_average"].tick_params(left=False, bottom=True)

            axes["diff_to_average"].set_xticks(x_tickss)
            axes["diff_to_average"].set_title("Diff to average")

            axes["diff_to_average"].axhline(0, color="black", linewidth=2)

            try:
                df.plot(y=columns_plot["diff_to_average"], kind="line", ax=axes["diff_to_average"], grid=True)
            except Exception as err:
                logger.error(f"plot {(pair1, pair2)} error: {str(err)}")

        # plot PROFIT ==============================================================================================
        if columns_plot["profit"]:
            axes["profit"].set_xticklabels([])
            axes["profit"].tick_params(left=False, bottom=False)

            axes["profit"].set_xticks(x_tickss)
            axes["profit"].set_title("profit")

            axes["profit"].axhline(0, color="black", linewidth=2)

            try:
                df.plot(y=columns_plot["profit"], kind="line", ax=axes["profit"], grid=True)
            except Exception as err:
                logger.error(f"plot {(pair1, pair2)} error: {str(err)}")

        # plot VOLUMES ============================================================================================
        if columns_plot["volume"]:
            axes["volume"].set_xticklabels(x_tickss)
            axes["volume"].tick_params(left=False, bottom=True)

            axes["volume"].set_yscale("log")

            axes["volume"].set_xticks(x_tickss)
            axes["volume"].set_title("volumes")

            try:
                df.plot(y=columns_plot["volume"], kind="line", ax=axes["volume"], grid=True, linewidth=3)
            except Exception as err:
                logger.error(f"plot {(pair1, pair2)} error: {str(err)}")

            d = df.index
            for column in columns_plot["volume"]:
                axes["volume"].fill_between(
                    d,
                    df[column],
                    alpha=0.2,
                    interpolate=True,
                )

        # save ====================================================================================================
        fig.tight_layout()
        files.append(os.path.join(dir_results_name, f"arb_pair_corr_{i+1}_{len(pair_combinations)}.pdf"))
        fig.savefig(files[-1], bbox_inches="tight")
        plt.close(fig)

    # combine all files into one
    if files and os.path.exists(file_name):
        os.remove(file_name)
    if len(files) > 1:
        utils.merge_pdfs(files, file_name)
    elif len(files) == 1:
        os.rename(files[0], file_name)

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
            # if "USDC" in symbol:
            #     continue
            if "USDT" in symbol:
                pairs_USDT.append(symbol)

    pairs_no_USDT = []
    for market in markets:
        if market["spot"] and market["type"] == "spot":
            symbol = market["symbol"]
            if "/" not in symbol:
                continue
            # if "USDC" in symbol:
            #     continue
            # if "EUR" in symbol:
            #     continue
            if "USDT" not in symbol:
                pairs_no_USDT.append(symbol)

    return pairs_USDT, pairs_no_USDT


def download_pairs_data_sorted_by_non_zero_volume(exchange, pairs, timeframe, limit) -> typing.Dict[str, pd.DataFrame]:
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

    logger = mp_logging.LoggerWorker().getLogger(__name__)

    _p_data = {}
    ranked_volume_pairs = []
    for i, pair in enumerate(pairs):
        logger.info(f"\tgetting pair data ({i+1} of {len(pairs)}) : {pair}")
        _p_data[pair] = get_ohlcv(exchange, pair, timeframe, limit)
        if _p_data[pair] is None:
            logger.info("\t\t\tno data")
            continue
        score = _p_data[pair][pair + "_VOLUME"].astype(bool).sum()
        ranked_volume_pairs.append((pair, score))
    ranked_volume_pairs.sort(key=lambda x: x[1], reverse=True)

    logger.info("rank pairs by non zero volume: ")
    p_data = {}
    for pair, score in ranked_volume_pairs:
        logger.info(f"\t\t{pair}: {score}")
        p_data[pair] = _p_data[pair]

    return p_data


def build_report(
    stock_name,
    timeframe,
    limit,
    pair_combinations: typing.List[PairsComb] | None,
    all_on_one: typing.Dict[str, pd.DataFrame],
    p_data: typing.Dict[str, pd.DataFrame],
):
    logger = mp_logging.LoggerWorker().getLogger(__name__)

    dir_results_name = "arb_pairs_corr_results"
    if not os.path.exists(dir_results_name):
        os.mkdir(dir_results_name)
    else:
        shutil.rmtree(dir_results_name)
        os.mkdir(dir_results_name)

    files = []
    files.append(os.path.join(dir_results_name, f"_arbitrage_corr_all_{stock_name}_{timeframe}_{limit}.pdf"))

    pair_combinations_for_all_on_one = []
    for name in all_on_one:
        pair_combinations_for_all_on_one.append(
            PairsComb(pair1=name, pair2=None, properties={"name": name, "size": all_on_one[name].shape[1]})
        )

    logger.info(f"visualise all_on_one")
    visualize_line_by_line(file_name=files[-1], p_data=all_on_one, pair_combinations=pair_combinations_for_all_on_one)

    if pair_combinations:
        files.append(os.path.join(dir_results_name, f"_arbitrage_corr_{stock_name}_{timeframe}_{limit}.pdf"))

        logger.info(f"visualise pair_combinations")
        visualize_line_by_line(file_name=files[-1], p_data=p_data, pair_combinations=pair_combinations)

        #
        # logger.info("generating plots...")
        # with concurrent.futures.ProcessPoolExecutor(max_workers=os.cpu_count()) as executor:
        #     for rank, ((sn1, sn2), p_data_for_plot, avg_profit) in enumerate(stocks_ranked):
        #
        #         # drop columns not related to sn1, sn2
        #         _pp = {}
        #         for pair in p_data_for_plot.keys():
        #             _pp[pair] = p_data_for_plot[pair].copy(deep=True)
        #             cols = [x for x in _pp[pair].columns.tolist() if
        #                     not x.startswith(sn1) and not x.startswith(sn2)]
        #             _pp[pair] = _pp[pair].drop(cols, axis=1)
        #
        #         future = executor.submit(
        #             visualize_line_by_line,
        #             **{
        #                 "data_dict": _pp,
        #                 "dir_results_name": dir_results_name,
        #                 "file_name": f"00{rank + 1}_arbitrage_{sn1}_{sn2}_{timeframe}_{limit}",
        #                 "label": f"\t\tplotting for stocks {sn1} {sn2} ({rank + 1} of {len(stock_combs)})",
        #                 "logging_queue": logging_queue,
        #             },
        #         )

    #
    # text = f"""
    # \t\t\t***********************************
    # \t\t\t*  Triangular arbitrage research  *
    # \t\t\t***********************************
    #
    # Warning: No fees are included!
    # Warning: Due to the sequential pair data downloading - there might be a lag between different pairs.
    #          Because the algorithm is using integer index instead of time
    #
    # date: {utils.datetime_to_text(utils.datetime_now())}
    #
    # stock name: {stock_name}
    # timeframe: {timeframe}
    # limit: {limit}
    #
    # pairs on stock: USDT size: {len(pairs_USDT)}
    # pairs on stock: no USDT size: {len(pairs_no_USDT)}
    #
    # total unique pairs using in sequences: {len(uniq_pairs)}
    # total possible sequences: {len(sequences)}
    #
    # Fetched data: now - timeframe * limit
    # =====================================
    #
    # available data for pairs, size: {len([x for x in p_data.keys() if p_data[x] is not None])}
    # available (USDT - pair - USDT) sequences: {len(list(s_data.keys()))}
    #
    # Sequences best to trade (from best to worse), score=number of non zero profit trades: ({len(seqs_non_zero_profits_dropped_0)})
    # {"\n\t".join([f"{int(x[1])}\t\t{'\t'.join(x[0])}" for x in seqs_non_zero_profits_dropped_0])}
    #
    # Plot legend for "profit" graph:
    #     "bv" - buy_buy_sell - not enough volume
    #     "b" - buy_buy_sell - profit
    #
    #     "sv" - buy_sell_sell - not enough volume
    #     "s" - buy_sell_sell - profit
    #
    #     "n" - no profit by both buy_buy_sell and buy_sell_sell
    #
    #     "i" - wrong index
    #     "p" - wrong price
    #     "v" - wrong volume
    #
    # """
    #
    # utils.create_pdf("first_page.pdf", text)
    #
    rep_file = os.path.join(dir_results_name, f"arbitrage_pair_corr_{stock_name}_{timeframe}_{limit}.pdf")

    utils.merge_pdfs(
        files,
        rep_file,
    )

    logger.info(f"report file: {rep_file}")

    # return rep_file


def find_correlations_between_pairs(p_data: typing.Dict[str, pd.DataFrame]) -> typing.List[PairsComb]:
    logger = mp_logging.LoggerWorker().getLogger(__name__)

    logger.info("calculating correlations")

    pair_combinations = list(itertools.combinations(p_data.keys(), 2))

    pair_combinations_corr = []
    for i, (pair1, pair2) in enumerate(pair_combinations):
        # logger.info(f"{i+1} of {len(pair_combinations)}: {(pair1, pair2)}")
        pair_combinations_corr.append(
            PairsComb(
                pair1=pair1,
                pair2=pair2,
                properties={
                    "pearson": p_data[pair1][pair1 + "_CLOSE"].corr(p_data[pair2][pair2 + "_CLOSE"]),
                    "kendall": p_data[pair1][pair1 + "_CLOSE"].corr(p_data[pair2][pair2 + "_CLOSE"], method="kendall"),
                    "spearman": p_data[pair1][pair1 + "_CLOSE"].corr(
                        p_data[pair2][pair2 + "_CLOSE"], method="spearman"
                    ),
                },
            )
        )

    pair_combinations_corr.sort(key=lambda x: x.properties["pearson"], reverse=True)

    logger.info(f"found all combinations: {len(pair_combinations_corr)}")

    return pair_combinations_corr


def filter_by_threshold(
    pair_combinations_corr: typing.List[PairsComb], threshold_down: float | None, threshold_up: float = None
) -> typing.List[PairsComb]:
    logger = mp_logging.LoggerWorker().getLogger(__name__)

    pair_combinations_filtered = []

    for two_pairs in pair_combinations_corr:
        if threshold_down and two_pairs.properties["pearson"] < threshold_down:
            continue
        if threshold_up and two_pairs.properties["pearson"] > threshold_up:
            continue
        pair_combinations_filtered.append(two_pairs)

    if threshold_down or threshold_up:
        logger.info(f"threshold_up: {threshold_up}")
        logger.info(f"threshold_down: {threshold_down}")
        logger.info(f"filtered by threshold combinations: {len(pair_combinations_filtered)}")

    return pair_combinations_filtered


def normalize(sr: pd.Series):
    # minmax
    # df[c]=(df_orig[c] - df_orig[c].mean()) / (df_orig[c].max() - df_orig[c].min())
    # Z-normalization
    return (sr - sr.mean()) / sr.std()


def calculate_normalized(p_data: typing.Dict[str, pd.DataFrame], pair_combinations: typing.List[PairsComb]):
    """
    Calculate normalized df in p_data

    inplace
    """
    _pr = set()
    for i, two_pairs in enumerate(pair_combinations):
        for pair in [two_pairs.pair1, two_pairs.pair2]:
            if pair not in _pr:
                p_data[pair][pair + "_NORM"] = normalize(p_data[pair][pair + "_CLOSE"])
                _pr.add(pair)


def turn_into_all_in_one(p_data: typing.Dict[str, pd.DataFrame], pairs, label) -> pd.DataFrame:
    """
    Combine `p_data` in `all_on_one` filtered by `pairs`

    And calculate average from all pairs
    """
    logger = mp_logging.LoggerWorker().getLogger(__name__)

    all_on_one = pd.DataFrame()
    for pair in pairs:
        if pair in p_data:
            all_on_one[pair + "_NORM"] = p_data[pair][pair + "_NORM"]
    n_of_used_pairs = all_on_one.shape[1]
    logger.info(f"number of USED pairs of {label}: {n_of_used_pairs} of {len(pairs)}")

    def weighted_average(df: pd.Series):
        weighted_avg = np.average(df.values)
        return pd.Series(
            [
                weighted_avg,
            ],
            index=["AVERAGE"],
        )

    # weighted average
    all_on_one["AVERAGE"] = all_on_one.apply(weighted_average, axis=1)

    return all_on_one


def add_average(p_data: typing.Dict[str, pd.DataFrame], all_on_one: pd.DataFrame):
    for pair in p_data:
        p_data[pair]["AVERAGE"] = all_on_one["AVERAGE"]
        p_data[pair][pair + "_DIFF_TO_AV"] = p_data[pair][pair + "_NORM"] - all_on_one["AVERAGE"]


def main(stock_name, timeframe, limit):
    logger_listener = mp_logging.LoggerListener()
    logging_queue = logger_listener.start_listener_process(log_file_path="arbitrage_pair_correlations.log")
    logger = mp_logging.LoggerWorker().getLogger(__name__)
    logger.info("start")

    exchange = getattr(ccxt, stock_name)()

    logger.info(f"timeframe: {timeframe}")
    logger.info(f"limit: {limit}")

    logger.info(f"stock_name: {stock_name}")
    pairs_USDT, pairs_no_USDT = get_pairs_no_USDT_spot(exchange)

    pairs_USDT = pairs_USDT[:30]
    pairs_no_USDT = pairs_no_USDT[:30]
    pairs = pairs_no_USDT + pairs_USDT
    # pairs = pairs_USDT

    logger.info(f"pairs size: {len(pairs)}")

    p_data = download_pairs_data_sorted_by_non_zero_volume(exchange, pairs, timeframe, limit)

    pair_combinations_corr = find_correlations_between_pairs(p_data)  # sorted by pearson
    calculate_normalized(p_data, pair_combinations_corr)

    # And calculate average from all pairs
    all_on_one = turn_into_all_in_one(p_data, pairs_USDT, label="pairs_USDT")
    # all_on_one = turn_into_all_in_one(p_data, pairs_no_USDT, label="pairs_no_USDT")

    pair_combinations_corr_filtered = filter_by_threshold(
        pair_combinations_corr, threshold_down=0.97
    )  # , threshold_up=0.98)

    add_average(p_data, all_on_one)

    all_on_one = {"pairs_USDT": all_on_one}

    build_report(
        stock_name,
        timeframe,
        limit,
        pair_combinations=pair_combinations_corr_filtered,
        all_on_one=all_on_one,
        p_data=p_data,
    )

    logger_listener.stop_listener_process()


if __name__ == "__main__":
    main(stock_name="bybit", timeframe="1m", limit=1000)

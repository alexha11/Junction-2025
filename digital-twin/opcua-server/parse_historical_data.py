import pandas as pd

HIST_DATA_FILE_PATH: str = "./data/historical-data-input.xlsx"
CLEANED_COL_NAMES_FILE_PATH: str = "./data/historical-data-clean-col-names.txt"
PARQUET_DATA_FILE_PATH: str = "./data/historical-data.parquet"


def clean_columns(cols):
    return (
        cols.str.strip()
        .str.lower()
        .str.replace(r"\s+", "_", regex=True)
        .str.replace(r"[^a-z0-9_]", "", regex=True)
        .str.replace(r"_+", "_", regex=True)
        .str.strip("_")
    )


def load_dataframe() -> pd.DataFrame:
    hist_df_raw = pd.read_excel(HIST_DATA_FILE_PATH, header=[0], skiprows=[1])
    hist_df_raw.columns = clean_columns(hist_df_raw.columns)

    # Check col names
    with open(CLEANED_COL_NAMES_FILE_PATH, "w", encoding="utf-8") as f:
        for col in hist_df_raw.columns:
            f.write(col + "\n")

    hist_df_raw["time_stamp"] = pd.to_datetime(
        hist_df_raw["time_stamp"], format="%d.%m.%Y %H.%M.%S", errors="coerce"
    )

    hist_df = (
        hist_df_raw.dropna(subset=["time_stamp"]).set_index("time_stamp").sort_index()
    )
    return hist_df


if __name__ == "__main__":
    df: pd.DataFrame = load_dataframe()
    df.to_parquet(PARQUET_DATA_FILE_PATH)
    print("Saved df to parquet file:", PARQUET_DATA_FILE_PATH)

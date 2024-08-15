# THere most be a smarter way to do this...
import xmltodict
import requests
import polars as pl
import json
import time
from tqdm import tqdm
from natsort import natsorted
from concurrent.futures import ThreadPoolExecutor
import argparse

def get_sra_run_metadata(sra_run_id, n_tries=3):
    """
    Fetch metadata for an SRA run from the SRA Database Backend API.
    
    Args:
    - sra_run_id (str): The SRA run ID.
    - n_tries (int, optional): The number of times to retry if the request fails. Defaults to 3.
    
    Returns:
    - dict: The metadata for the SRA run.
    """
    base_url = "https://trace.ncbi.nlm.nih.gov/Traces/sra-db-be/run_new?"
    params = {
        "acc": sra_run_id,
        "format": "json"
    }
    response = requests.get(f"{base_url}", params=params)
    if response.status_code == 200:
        metadata = xmltodict.parse(response.content.decode())["RunBundle"]["RUN"]
        return metadata
    elif n_tries > 0:
        print(f"Error: {response.status_code} ({response.text})")
        print(f"Retrying in 20 seconds ({n_tries} tries left)…")
        time.sleep(20)
        return get_sra_run_metadata(sra_run_id, n_tries - 1)
    else:
        return f"Error: {response.status_code}, {response.text}"

def process_sra_run_chunk(sra_run_ids_chunk):
    """
    Process a chunk of SRA run IDs and fetch their metadata.
    
    Args:
    - sra_run_ids_chunk (list): A list of SRA run IDs.
    
    Returns:
    - list: A list of metadata dictionaries.
    """
    chunk_data = []
    for sra_run_id in sra_run_ids_chunk:
        try:
            metadata = get_sra_run_metadata(sra_run_id)
            chunk_data.append(metadata)
        except Exception as e:
            print(f"Error fetching metadata for {sra_run_id}: {e}")
    return chunk_data

def main(input_file, output_json,  chunk_size=100, max_workers=5,column_name="subjectID"): #output_csv,
    """
    Main function to fetch metadata for SRA runs and save to JSON and CSV files.
    
    Args:
    - input_file (str): The input TSV file containing SRA run IDs.
    - output_json (str): The output JSON file to save the metadata.
    - output_csv (str): The output CSV file to save the metadata.
    - chunk_size (int, optional): The size of each chunk of SRA run IDs. Defaults to 100.
    - max_workers (int, optional): The maximum number of worker threads. Defaults to 5.
    """
    metadata_df = pl.read_csv(input_file, separator="\t", null_values="NULL")
    sra_run_ids = natsorted(metadata_df.get_column(column_name).unique())

    chunks = [sra_run_ids[i:i + chunk_size] for i in range(0, len(sra_run_ids), chunk_size)]
    data = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_sra_run_chunk, chunk): chunk for chunk in chunks}
        for future in tqdm(futures, ncols=80, smoothing=0):
            chunk = futures[future]
            try:
                result = future.result()
            except Exception as e:
                print(f"Error processing chunk: {e}")
            else:
                data.extend(result)

    with open(output_json, "w") as fo:
        json.dump(data, fo, indent=2)

    # tmpdf = pl.from_dicts(data,infer_schema_length=123,strict=True) # Bugged
    # tmpdf.write_csv(output_csv)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch metadata for SRA runs from SRA Database Backend API")
    parser.add_argument("-i", "--input_file", required=True, help="Input TSV file containing SRA run IDs")
    parser.add_argument("-j", "--output_json", required=True, help="Output JSON file to save the metadata")
    # parser.add_argument("-c", "--output_csv", required=True, help="Output CSV file to save the metadata")
    parser.add_argument("-s", "--chunk_size", type=int, default=100, help="Size of each chunk of SRA run IDs")
    parser.add_argument("-w", "--max_workers", type=int, default=5, help="Maximum number of worker threads")
    parser.add_argument("-n", "--column_name", type=int, default="subjectID", help="name of column/field in file that has lists the SRA run IDs")

    args = parser.parse_args()
    main(args.input_file, args.output_json,  args.chunk_size, args.max_workers, args.column_name) #args.output_csv,

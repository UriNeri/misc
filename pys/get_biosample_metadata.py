# Inspired and made with help from Antônio Camargo https://github.com/apcamargo
import requests
import polars as pl
import json
import time
from tqdm import tqdm
from natsort import natsorted
from concurrent.futures import ThreadPoolExecutor
import argparse

def get_biosample_metadata(biosample_id, n_tries=3):
    """
    Fetch metadata for a BioSample from the ENA API.
    
    Args:
    - biosample_id (str): The BioSample accession ID.
    - n_tries (int, optional): The number of times to retry if the request fails. Defaults to 3.
    
    Returns:
    - dict: The metadata for the BioSample.
    """
    base_url = "https://www.ebi.ac.uk/ena/portal/api/filereport"
    value_backlist = {
        "",
        "missing",
        "not available",
        "not determined",
        "not applicable",
        "not collected",
        "na",
    }
    params = {
        "accession": biosample_id,  
        "result": "sample",  
        "format": "json",  
        "fields": "all",  
    }
    response = requests.get(base_url, params=params)
    if response.status_code == 200:
        metadata = response.json()
        metadata = {
            k: v for k, v in metadata[0].items() if v.casefold() not in value_backlist
        }
        return metadata
    elif n_tries > 0:
        print(f"Error: {response.status_code} ({response.text['message']})")
        print(f"Retrying in 20 seconds ({n_tries} tries left)…")
        time.sleep(20)
        return get_biosample_metadata(biosample_id, n_tries - 1)
    else:
        return f"Error: {response.status_code}, {response.text}"

def processChunk(biosample_ids_chunk):
    """
    Process a chunk of BioSample IDs and fetch their metadata.
    
    Args:
    - biosample_ids_chunk (list): A list of BioSample IDs.
    
    Returns:
    - list: A list of metadata dictionaries.
    """
    chunk_data = []
    for biosample_id in biosample_ids_chunk:
        try:
            metadata = get_biosample_metadata(biosample_id)
            chunk_data.append(metadata)
        except Exception as e:
            print(f"Error fetching metadata for {biosample_id}: {e}")
    return chunk_data

def main(input_file, output_json, output_csv, chunk_size=100, max_workers=5):
    """
    Main function to fetch metadata for BioSamples and save to JSON and CSV files.
    
    Args:
    - input_file (str): The input TSV file containing BioSample IDs.
    - output_json (str): The output JSON file to save the metadata.
    - output_csv (str): The output CSV file to save the metadata.
    - chunk_size (int, optional): The size of each chunk of BioSample IDs. Defaults to 100.
    - max_workers (int, optional): The maximum number of worker threads. Defaults to 5.
    """
    metadata_df = pl.read_csv(input_file, separator="\t", null_values="NULL").filter(pl.col("BioSample").is_not_null())
    biosamples = natsorted(metadata_df.get_column("BioSample").unique())

    chunks = [biosamples[i:i + chunk_size] for i in range(0, len(biosamples), chunk_size)]
    data = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(processChunk, chunk): chunk for chunk in chunks}
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

    tmpdf = pl.from_dicts(data)
    tmpdf.write_csv(output_csv)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch metadata for BioSamples from ENA API")
    parser.add_argument("-i", "--input_file", required=True, help="Input TSV file containing BioSample IDs")
    parser.add_argument("-j", "--output_json", required=True, help="Output JSON file to save the metadata")
    parser.add_argument("-c", "--output_csv", required=True, help="Output CSV file to save the metadata")
    parser.add_argument("-s", "--chunk_size", type=int, default=100, help="Size of each chunk of BioSample IDs")
    parser.add_argument("-w", "--max_workers", type=int, default=5, help="Maximum number of worker threads")
    args = parser.parse_args()
    main(args.input_file, args.output_json, args.output_csv, args.chunk_size, args.max_workers)

# Data Analysis

## Folder organization

* `data/smc` : MySQL scripts to initialize local databases
* `src`
	* `src/analysis` : Python modules to manipulate 802.11 scan and connectivity data.
	* `src/analysis/smc` : SMC data analysis.
	* `src/analysis/trace` : Trace-based analysis for mobile connectivity collections.
	* `src/analysis/trace/ap_selection` : Simulation of different AP selection schemes
	* `src/analysis/trace/utils` : Auxiliary Python modules used by `ap_selection` scripts.

* `utils` : General auxiliary Python modules (e.g., interface to HDFS file operations, manipulation of GPS data, manipulation of .pcap files, etc.).
	* `utils/ieee80211` : Decode 802.11 frame fields from capture files in .csv format.
	* `utils/mapping` : Manipulate GPS data and interact with OpenStreetMap APIs.
* `plot` : Code for plotting data processed by `analysis` scripts.
	
## Main scripts

#### `analyze-mimo.py`

Analyze MU-MIMO experiment data and generate the results given in these documents: [1](https://www.andrew.cmu.edu/user/antonior/files/2019-05-15-meeting.pdf), [2](https://www.andrew.cmu.edu/user/antonior/files/report-variability.pdf), [3](https://www.andrew.cmu.edu/user/antonior/files/report-overhead.pdf). It uses the custom `utils.ieee80211.ac` module to decode VHT MU beamforming reports.

The experimental data consumed by the script is available [here](https://mega.nz/#!ieRwmSjI!J1k-qFBlXuFNox2ho8bWxIX2ySI1SDZgyuVrx_qEoQg). **todo : add description of data.**

To run the script, run:

```
python analyze-mimo.py --input-dir <path-to-experimental-data-folder> --graphs-dir <any-dir-of-your-choice>
```

I encourage you to look at the script and (un)comment the different functions under `__main__` to generate different results. **todo : add breif description of methods in the script as comments.**

#### `analyze-auth.py`

Analyze authentication delays in public networks in Porto, namely FON. Used to generate results in these documents: [1](https://www.dropbox.com/s/isx16i01vdtfzvn/meeting-2019-04-10.pdf?dl=0).

#### `analyze-smc.py`

Analysis of 'Sense My City' data, in order to generate the results (and more) present in section 1.2 of my Ph.D. proposal, available [here](https://www.andrew.cmu.edu/user/antonior/files/proposal.pdf). 
This includes analysis of:

* Extent and quality of WiFi signal coverage in Porto roads for different ISPs
* Handoff behavior in urban roads, including 'time budgets' for handoffs, estimations of number of handoffs, for different ISPs

The script depends on several custom Python modules and extracts data from both MySQL and HDFS databases, which can make it a bit confusing. A more detailed description of how it works is given [here]().

#### `analyze-trace.py`, `analyze-traces.py` and `manage-trace.py`

**DEPRECATED:** I recommend you to use the Jupyter notebook scripts instead, available [here](https://github.com/adamiaonr/wifi-vehicles/tree/master/ap-selection/datarate-estimation).

Scripts to analyze mobile connectivity traces using 802.11n APs. The traces were captured while riding a bicycle in FEUP back in January 2019.


## Auxiliary Python modules

TODO

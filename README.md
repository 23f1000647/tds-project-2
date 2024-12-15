# tds-project-2
Data Analysis using LLM for TDS Project 2

## Steps
1. Load the input file
2. Query LLM for metadata based on the input data sample shared, get following information for each features
    *  Feature / Column Name
    *  Data Type
    *  Min value (that feature could possibly take)
    *  Stats (could stats be performed for that feature)
3.  Perform descriptive statistics of all numerical columns
    *  Basic descriptive stats info
    *  Also Include count of Null values for that feature
    *  Also Include count of out of range value for that feature
4.  Perform preprocessing steps
    *  Impute Numerical columns with NaN values SimpleImputer with strategy mean
    *  Set out of range values to NaN (those values below Min value that column could take)
    *  Drop all Nan values for all the columns
5.  Correlation
    *  Perform orrelation for all numerical column
    *  Generate Correlation HeatMap
    *  Filter only high correlation features to send to LLM for analysis
6.  Outlier detection
    *  Perform zscore for all numerical columns and get those outliers for each column
    *  Prepare chart cpturing all outliers and save the chart
7.  Get summary so far
    *  Pass all above info to LLM and ask for introduction and summary texts
8.  Perform KMeans clustering and get PCA done
    *  Plot first 2 principle components and save chart
9.  Check if the data need one of timeseries or geospatial or network analysis
    *  Request LLM for code for one of the case and execute code
    *  Output shall save the chart generated
10.  Ask LLM to summarize the image generated in above step
11.  Provide all the details like column, data types, outliers, correlation etc and ask LLM to provide overall narration for each steps and also final summary text
12.  Write all outputs to README.md file
  
   
   

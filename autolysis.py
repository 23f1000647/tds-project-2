# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "httpx",
#   "pandas",
#   "requests",
#   "numpy",
#   "seaborn",
#   "chardet",
#   "scikit-learn",
#   "geopandas",
#   "scipy",
#   "matplotlib"
# ]
# ///

import pandas as pd
import numpy as np
import chardet
import requests
import os
import json
import sys
import traceback
import io
import base64
from sklearn.impute import SimpleImputer
from sklearn.compose import ColumnTransformer
import geopandas as gpd
from scipy.stats import zscore
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA

AIPROXY_TOKEN = os.getenv("AIPROXY_TOKEN")
MAX_RETRY = os.getenv("MAX_RETRY", 3)
AIPROXY_URL = os.getenv("AISERVER_URL","https://aiproxy.sanand.workers.dev/openai/v1/chat/completions")
MODEL = os.getenv("AI_MODEL","gpt-4o-mini")
HEADERS = {
    'Authorization': f'Bearer {AIPROXY_TOKEN}',
    'Content-Type': 'application/json'
}
OUTPUT_FILE = "README.md"

FUNCTIONS_DESCRIPTIONS_DICT = {
    'get_column_dtypes': [
        {
            'name':'get_column_dtypes',
            'description':'Identify column name, its data types and also determine the possible minimum value the column could take inferred based on column name',
            'parameters':{
                'type':'object',
                'properties':{
                    'column_metadata':{
                        'type':'array',
                        'description':'Metadata for each column',
                       'items':{
                            'type':'object',
                            'properties':{
                               'name':{
                                    'type':'string',
                                   'description':'Name of the column'
                               },
                               'type':{
                                    'type':'string',
                                    'description':'Inferred data type of the column based on its values and name. Valid types include integer, float, datetime, string, boolean, object'
                                },
                                'description':{
                                    'type': 'string',
                                    'description': 'Brief description of what this column signifies'
                                },
                                'min_value': {
                                    "oneOf": [
                                      { "type": "integer" },
                                      { "type": "number" }
                                    ],
                                    'description': 'Logical minimum value this column could take (e.g., age >= 0). Applicable only for numeric data types'
                                },
                                'stats': {
                                    'type': 'boolean',
                                    'description':'Determine if the column is suitable for descriptive statistics (True/False) using the following guidelines: Numerical or continuous data is preferred, Identifiers or purely categorical data should not be considered, Consider the analytical value of data and relevance to potential use cases'
                                }
                            },
                            'required':['column_name','column_type','description','stats']
                        },
                        'minItems':1
                    }
                },
                'required':['column_metadata']
            }
        }
    ],
    'get_intro_stats_summary': [
        {
            "name": "get_intro_stats_summary",
            "description": "Generate a title, introduction, and a brief summary of observations for a dataset as well as the next few prompts to ask LLM for further analysis",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "A concise and relevant title for the dataset based on its subject or purpose."
                    },
                    "introduction": {
                        "type": "string",
                        "description": "A short introduction providing an overview of the dataset, its structure, and what it represents."
                    },
                    "summary": {
                        "type": "string",
                        "description": "Key observations and inferences from the provided descriptive statistics, highlighting any significant patterns, trends, or anomalies."
                    },
                    "time_series": {
                        "type": "object",
                        "description": "Time series data analysis",
                        "properties": {
                            "isavailable": {
                                "type": "boolean",
                                "description": "Indicate if the dataset contains time series data."
                            },
                            "prompt": {
                                "type": "string",
                                "description": "If exist, Best prompt to ask LLM for further analysis."
                            }
                        },
                        "required": ["isavailable", "prompt"]
                    },
                    "geospatial": {
                        "type": "object",
                        "description": "Geospatial data analysis",
                        "properties": {
                            "isavailable": {
                                "type": "boolean",
                                "description": "Indicate if the dataset contains geospatial data."
                            },
                            "prompt": {
                                "type": "string",
                                "description": "If exist, Best prompt to ask LLM for further analysis."
                            }
                        },
                        "required": ["isavailable", "prompt"]
                    },
                    "network": {
                        "type": "object",
                        "description": "Network data analysis",
                        "properties": {
                            "isavailable": {
                                "type": "boolean",
                                "description": "Indicate if the dataset contains data for network analysis."
                            },
                            "prompt": {
                                "type": "string",
                                "description": "If exist, Best prompt to ask LLM for further analysis."
                            }
                        },
                        "required": ["isavailable", "prompt"]
                    }
                },
                "required": ["title", "introduction", "summary", "time_series", "geospatial", "network"]
            }
        }
    ],
    'get_code_for_analysis': [
        {
            'name':'get_code_for_analysis',
            'description':'Respond with python code for the given prompt, Do not include any comment blocks except code',
            'parameters':{
                'type':'object',
                'properties':{
                    'python_code':{
                        'type':'string',
                        'description':'Python code that can be executed programatically for the given prompt'
                    },
                    'output_file':{
                        'type':'string',
                        'description':'Name of the output file to save the generated chart'
                    },
                    'title': {
                        'type': 'string',
                        'description': 'Provide a title for the analysis'
                    },
                    'rationale': {
                        'type': 'string',
                        'description': 'Provide details description about the analysis and the rationale'
                    }
                },
                'required':['python_code','output_file','title','rationale']
            }
        }
    ],
    'get_feedback': [
        {
            'name':'get_feedback',
            'description':'From the given image, provide the inference or insights based on the input image shared',
            'parameters':{
                'type':'object',
                'properties':{
                    'inference': {
                        'type': 'string',
                        'description': 'What is happening in the image?'
                    },
                    'insights': {
                        'type': 'string',
                        'description': 'Why this is happening?'
                    },
                    'recommendations': {
                        'type': 'string',
                        'description': 'What to do next?'
                    }
                },
                'required':['rationale','inference']
            }
        }
    ],
    'get_narrative': [
        {
            'name':'get_narrative',
            'description':'From the given details, provide a narrative or story based on the input shared',
            'parameters':{
                'type':'object',
                'properties':{
                    'preprocessing': {
                        'type': 'string',
                        'description': 'Narrate the outcome of the preprocessing steps outcome'
                    },
                    'correlation': {
                        'type': 'string',
                        'description': 'Narrate the story of the correlation analysis outcome'
                    },
                    'outliers': {
                        'type': 'string',
                        'description': 'Narrate the story of the outliers analysis outcome'
                    },
                    'cluster': {
                        'type': 'string',
                        'description': 'Narrate the story of the cluster analysis outcome'
                    },
                    'summary': {
                        'type': 'string',
                        'description': 'Narrate the overall summary of the analysis explaining the insights and recommendations'
                    }
                },
                'required':['rationale','inference']
            }
        }
    ]
}

METADATA_INSTRUCTION = (
      "Analyze the dataset's initial lines, starting with the header followed by sample data"
      "Extract column names from the header and infer each column's data type based on values and names"
      "Estimate the minimum possible value for each column using its name" 
      "Assess if each column is suitable for descriptive statistics (True/False): Preferred: Numerical or continuous data, Exclude: Identifiers, purely categorical data, or irrelevant analytical data"
      "Use valid Python data types: integer, float, datetime, string, boolean, or object"
)

INTRO_AND_DESCRIPTIVE_STATS_INSTRUCTION = (
    "Analyze the dataset's metadata and descriptive statistics"
    "Suggest a concise, relevant title for the analysis"
    "Summarize the dataset, including its scope, purpose, and key attributes"
    "Highlight key observations from the descriptive statistics, noting trends, outliers, and patterns"
    "Based on metadata and statistics, identify if the dataset contains time series, geospatial, or network data and respond with prompts for further analysis"
)

GENERIC_CODE_INSTRUCTION = (
    "Return only Python code, without comments"
    "Assume the dataset is available in a DataFrame named 'df'; do not create synthetic data"
    "Use the provided column or feature names exactly as given"
    "Do not display the chart; export it directly as a PNG file"
    "Use Seaborn for all plotting tasks"
)

ADVANCED_ANALYSIS_INSTRUCTION = (
    "Code should check for unique values of thr column being used analysis"
    "If this is greater than a certain threshold, then use sorting to find the top 10 values"
)

CONCLUSION_PROMPT = (
    'Given the image, what do you infer from this'
    'Provide inference, insights and recommendations'
)


def getFileEncoding(filename):
    '''
    Method to get the file encoding to load using pandas
    Args: 
        filename: str: path to the file
    Returns:  
        str: encoding of the file
    '''
    with open(filename,"rb") as f:
        content = f.read() 
        return chardet.detect(content)['encoding']


def getFunctionDescriptions(functionName):
    '''
    Method to get the function description to be passed to LLM
    Args: 
        function_name: str: name of the function
    Returns:
        dict: description of the function
    '''
    return FUNCTIONS_DESCRIPTIONS_DICT[functionName]

def readImage(imagefile):
    '''
    Method to read the image file
    Args:
        imagefile: str: path to the image file
    Returns:
        bytes: image data
    '''
    try:
        with open(imagefile, 'rb') as file:
            image_data = file.read()
    except PermissionError as e:
        print(f"PermissionError: Ensure the file is not open elsewhere. {e}")
    except Exception as e:
        print(f"Error moving file: {e}")    
    return image_data

def createMessagePayload(instruction, userContent, imageFile):
    '''
    Method to create the message payload to be passed to LLM, including the image
    Args:
        instruction: str: instruction to be passed to LLM
        userContent: str: user content to be passed to LLM
        imageFile: str: path to the image file
    Returns:
        dict: message payload to be passed to LLM
    '''
    if imageFile == "":
        return [
            {'role':'system','content':instruction},
            {'role':'user','content':userContent}
        ]
    else:
        image_data = readImage(imageFile)
        mime_type = "image/png" if imageFile.endswith(".png") else "image/jpeg"
        base64_image = base64.b64encode(image_data).decode('utf-8')
        image_url = f"data:{mime_type};base64,{base64_image}"
        return [{
                'role':'user',
                'content': [{'type':'text','text':instruction},{'type':'image_url','image_url':{'detail':'low','url':image_url}}]
            }]
    
def getPayload(instruction, userContent, functionName, imageFile = ""):
    '''
    Method to get the payload to be passed to LLM
    Args:
        instruction: str: instruction to be passed to LLM
        userContent: str: user content to be passed to LLM
        functionName: str: name of the function to be called
        imageFile: str: path to the image file
    Returns:
        dict: payload to be passed to LLM
    '''
    function = getFunctionDescriptions(functionName)
    json_data={
        'model': MODEL,
        'messages': createMessagePayload(instruction, userContent, imageFile),
        'functions':function,
        'function_call': {'name':functionName}
    } 
    return json_data

def handleRequest(instruction, userContent, functionName):
    '''
    Method to call LLM
    Args:
        instruction: str: instruction to be passed to LLM
        userContent: str: user content to be passed to LLM
        functionName: str: name of the function to be called
    Returns:
        dict: response from LLM in JSON format
    '''
    json_data = getPayload(instruction, userContent, functionName)
    response = requests.post(AIPROXY_URL,headers=HEADERS,json=json_data)
    return response.json()

def loadFile(fileName):
    '''
    Method to load the file
    Args:
        fileName: str: path to the file
    Returns:
        DataFrame: dataframe loaded from the file
    '''
    try:
        encoding = getFileEncoding(fileName)
        df = pd.read_csv(fileName, encoding=encoding)
        return df
    except Exception as e:
        print(f"Error: {e}")

def getFeatureInfo(df):
    '''
    Method to get the feature information such as name, type, description, min_value, statistics could be calculated
    Args:
        df: DataFrame: dataframe to be analyzed
    Returns:
        dict: feature information
    '''
    featureInfo = handleRequest(METADATA_INSTRUCTION, df[0:7].to_csv(index=False), 'get_column_dtypes')
    return json.loads(featureInfo['choices'][0]['message']['function_call']['arguments'])['column_metadata']

def getMinValue(featureInfo, columnName):
    '''
    Method to get the minimum value for a column based on the feature information returned by LLM
    Args:
        featureInfo: dict: feature information
        columnName: str: column name
    Returns:
        int/float: minimum value for the column
    '''
    for item in featureInfo:
        if item['name'] == columnName:
            return item['min_value']
    
def getDescriptiveStats(df, featureInfo):
    '''
    Method to get the descriptive statistics for the dataframe
    Args:
        df: DataFrame: dataframe to be analyzed
        featureInfo: dict: feature information
    Returns:
        dict: descriptive statistics
    '''
    nullValues = df.isnull().sum().to_dict()
    columnForStats = [feature['name'] for feature in featureInfo if feature['stats']]
    descriptiveStats = df[columnForStats].describe().to_dict()
    for key, stats in descriptiveStats.items():
        if key in nullValues:
            stats['null'] = nullValues[key]
            stats['invalid'] = df[df[key] < getMinValue(featureInfo, key)].shape[0]
    return descriptiveStats

def dataPreprocessing(df, featureInfo, statsInfo):
    '''
    Method to preprocess the data, impute missing values and remove invalid values for numerical features and remove rows with missing values
    Args:
        df: DataFrame: dataframe to be analyzed
        featureInfo: dict: feature information
        statsInfo: dict: descriptive statistics
    Returns:
        DataFrame: preprocessed dataframe
    '''
    # Initialize counters
    dropped_rows = 0
    below_range_values = {col: 0 for col in statsInfo.keys()}

    # Impute missing numeric values with mean
    imputer = SimpleImputer(missing_values=np.nan, strategy='mean')
    transformer = ColumnTransformer([('impute', imputer, list(statsInfo.keys()))],
                                    remainder='passthrough', verbose_feature_names_out=False)
    df_imputed = transformer.fit_transform(df)
    df_imputed = pd.DataFrame(df_imputed, columns=transformer.get_feature_names_out())

    # Loop through columns and check for values below the minimum
    for col in df_imputed.columns:
        if col in statsInfo.keys():
            min_value = getMinValue(featureInfo, col)
            below_range = df_imputed[col] < min_value
            below_range_count = below_range.sum()  # Count of values below the minimum

            # Track how many values are below the minimum
            below_range_values[col] = below_range_count

            # Set values below the range to NaN
            df_imputed.loc[below_range, col] = np.nan

    # Drop rows with any NaN values
    dropped_rows = df_imputed.isna().sum(axis=1).sum()  # Count total NaN values (which will be dropped)
    df_imputed.dropna(inplace=True)
    update_details = {"dropped_rows": dropped_rows, "out_of_range_values": below_range_values}
    return df_imputed, update_details

def getSummaryAndNextSteps(df,statsInfo):
    '''
    Method to get the summary and next steps for the analysis
    Args:
        df: DataFrame: dataframe to be analyzed
        statsInfo: dict: descriptive statistics
    Returns:
        dict: summary and next steps
    '''
    content = f"Columns:{df.columns}\n\nData Types:{df.dtypes}\n\nStatistics: {statsInfo}"
    response = handleRequest(INTRO_AND_DESCRIPTIVE_STATS_INSTRUCTION, content, 'get_intro_stats_summary')
    print(response)
    arguments = json.loads(response['choices'][0]['message']['function_call']['arguments'])
    return arguments

def handleRequestAndExecute(instruction, content, functionName,df):
    '''
    Method to handle the request and execute the code returned by LLM
    Args:
        instruction: str: instruction to be passed to LLM
        content: str: content to be passed to LLM
        functionName: str: name of the function to be called
        df: DataFrame: dataframe to be analyzed
    Returns:
        str: title, output file, rationale
    '''
    response = handleRequest(instruction, content, functionName)
    codeBlock = ""
    error = ""
    attempt = 0
    flag = True
    # Loop to retry in case of any exception
    while ((attempt < MAX_RETRY) & flag):
        try:
            if attempt > 0:
              content = f"code={codeBlock}\nerror={error}"
              response = handleRequest(instruction, content, functionName)
            #Get the code block, output file and rationale from the response
            codeBlock = json.loads(response['choices'][0]['message']['function_call']['arguments'])['python_code']
            output_file = json.loads(response['choices'][0]['message']['function_call']['arguments'])['output_file']
            rationale = json.loads(response['choices'][0]['message']['function_call']['arguments'])['rationale']            
            title = json.loads(response['choices'][0]['message']['function_call']['arguments'])['title']
            # Execute the code block
            exec(codeBlock)
            flag = False
            return title, output_file, rationale
        except Exception as e:
            # Print the error and retry
            buffer = io.StringIO()
            traceback.print_exc(file=buffer)
            error = buffer.getvalue()
            print(f"Error: {error}")
            buffer.close()
        finally:
            attempt += 1

    return ""

def advancedAnalytics(df, statsInfo, summaryInfo):
    '''
    Method to perform analysis on the dataframe
    Args:
        df: DataFrame: dataframe to be analyzed
        statsInfo: dict: descriptive statistics
        summaryInfo: dict: summary and next steps
    Returns:
        list: analysis output
    '''
    content = f"Columns:{df.columns}\n\nData Types:{df.dtypes}\n\nStatistics: {statsInfo}"

    analysis_output = []
    if summaryInfo["time_series"]["isavailable"]:
        try:
            prompt = GENERIC_CODE_INSTRUCTION + ADVANCED_ANALYSIS_INSTRUCTION + summaryInfo['time_series']['prompt']
            title, output_file, rationale = handleRequestAndExecute(prompt,content,"get_code_for_analysis",df)
            analysis_output.append({"title":title, "output_file":output_file, "rationale":rationale})
        except Exception as e:
            print(f"Error: {e}")
    elif summaryInfo["geospatial"]["isavailable"]:
        try:
            prompt = GENERIC_CODE_INSTRUCTION  + ADVANCED_ANALYSIS_INSTRUCTION + summaryInfo['geospatial']['prompt']
            title, output_file, rationale = handleRequestAndExecute(prompt,content,"get_code_for_analysis",df)
            analysis_output.append({"title":title, "output_file":output_file, "rationale":rationale})
        except Exception as e:
            print(f"Error: {e}")
    elif summaryInfo["network"]["isavailable"]:
        try:
            prompt = GENERIC_CODE_INSTRUCTION  + ADVANCED_ANALYSIS_INSTRUCTION + summaryInfo['network']['prompt']
            title, output_file, rationale = handleRequestAndExecute(prompt,content,"get_code_for_analysis",df)
            analysis_output.append({"title":title, "output_file":output_file, "rationale":rationale})
        except Exception as e:
            print(f"Error: {e}")
    return analysis_output

def applyKMeansClustering(df, featureInfo, n_clusters=5):
    '''
    Apply KMeans clustering on the data and plot the clusters.
    Args:
        df: DataFrame: input data to be clustered
        featureInfo: dict: feature information
        n_clusters: int: number of clusters for KMeans
    Returns:
        dict: clusters information
    '''
    numerical_columns = [feature['name'] for feature in featureInfo if feature['stats']]
    df[numerical_columns] = df[numerical_columns].apply(pd.to_numeric, errors='coerce')

    print(numerical_columns)

    # Apply KMeans clustering
    kmeans = KMeans(n_clusters=n_clusters, random_state=42)
    df['Cluster'] = kmeans.fit_predict(df[numerical_columns])

    # Reduce dimensions to 2D using PCA for better visualization
    pca = PCA(n_components=2)
    pca_components = pca.fit_transform(df[numerical_columns]) # Exclude 'Cluster' from PCA
    print(pca_components.shape)

    # Create a new DataFrame for plotting
    df_pca = pd.DataFrame(pca_components, columns=['PC1', 'PC2'])
    df_pca['Cluster'] = df['Cluster']

    # Generate and save the cluster visualization chart
    output_file = "clusters.png"
    plt.figure(figsize=(10, 6))
    sns.scatterplot(data=df_pca, x='PC1', y='PC2', hue='Cluster', palette="viridis", s=100, marker='o', edgecolor='k', alpha=0.7)
    plt.title('KMeans Clustering (2D PCA Projection)', fontsize=16)
    plt.xlabel('PC1')
    plt.ylabel('PC2')
    plt.legend(title='Cluster')
    plt.tight_layout()
    plt.savefig(output_file)
    plt.close()

    clusters = df['Cluster'].value_counts().to_dict()
    clusterInfo = {"clusters":clusters, "output_file":output_file}
    return clusterInfo

def getHighCorrelation(df, featureInfo, threshold=0.8):
    '''
    Generate a correlation heatmap for the numerical columns in the dataframe
    and return significant correlations greater than a defined threshold.
    
    Args:
        df: DataFrame: Input dataframe with numerical columns
        threshold: float: Correlation threshold to consider for significance
    
    Returns:
        significant_corr: DataFrame: A DataFrame with significant correlations
    '''
    numerical_columns = [feature['name'] for feature in featureInfo if feature['stats']]
    df[numerical_columns] = df[numerical_columns].apply(pd.to_numeric, errors='coerce')
    # Compute the correlation matrix
    corr_matrix = df[numerical_columns].corr()

    output_file = "correlation_heatmap.png"
    # Generate the heatmap
    plt.figure(figsize=(10, 8))
    sns.heatmap(corr_matrix, annot=True, cmap='coolwarm', fmt='.2f', linewidths=0.5)
    
    # Add title and labels
    plt.title('Correlation Heatmap', fontsize=16)
    plt.tight_layout()
    plt.savefig(output_file)
    
    # Filter out correlations that are greater than the threshold (absolute value)
    # This will exclude the diagonal (self-correlations) and correlations below the threshold
    high_corr_matrix = corr_matrix.abs() > threshold
    high_corr_matrix = high_corr_matrix.where(high_corr_matrix).stack().reset_index()
    
    # Renaming columns for clarity
    high_corr_matrix.columns = ['Feature1', 'Feature2', 'Correlation']
    
    # Removing duplicate pairs (e.g., (A, B) and (B, A))
    high_corr_matrix = high_corr_matrix[high_corr_matrix['Feature1'] < high_corr_matrix['Feature2']]
    
    correlationInfo = {"high_corr_matrix":high_corr_matrix, "output_file":output_file}
    return correlationInfo

def addContentToReadme(content, section = f"# Title\n"):
    '''
    Method to add content to the README.md file
    Args:
        content: str: content to be added
        section: str: section to add the content
    '''
    try:
      with open(OUTPUT_FILE, "a") as file:
          print(file.name)
          if section == f"# Title\n":
            file.write("# "+content+"\n")
          elif (section == f"## Analysis\n"):
            if (content == ""):
              file.write(section)
            else:
              file.write(content+'\n')
          else:
            file.write(section)
            file.write(content+'\n')
    except Exception as e:
      print("Error writing to ReadMe",e)

def addTitle(content, section = f"# Title\n"):
    '''
    Method to add title to the README.md file
    Args:
        content: str: title content
        section: str: section to add the content
    '''
    addContentToReadme(content, section)

def addIntroduction(content, section = f"## Introduction\n"):
    '''
    Method to add introduction to the README.md file
    Args:
        content: str: introduction content
        section: str: section to add the content
    '''
    addContentToReadme(content, section)

def addMetaData(content, section = f"## Metadata\n"):
    '''
    Method to add metadata section to the README.md file
    Args:
        content: list: metadata content
        section: str: section to add the content
    '''
    table_header = "\n|Name  |Type  |Description  |\n|------|------|-------------|\n"
    table_rows = "\n".join([f"| {item['name']} | {item['type']} | {item['description']} |" for item in content])
    markdown_content = f"{table_header}{table_rows}"
    addContentToReadme(markdown_content, section)

def addAnalysisSection(correlationInfo, outliersInfo, clusterInfo, analysisSummary, narrative, section=f"## Analysis\n"):
    '''
    Method to add analysis section to the README.md file
    Args:
        correlationInfo: dict: correlation information
        outliersInfo: dict: outliers information
        clusterInfo: dict: cluster information
        narrative: dict: narrative information
        section: str: section to add the
    '''
    correlation_output_file = correlationInfo['output_file']
    markdown_content = f"\n\n### Correlation \n\nBelow is the correlation heatmap"
    markdown_content += f"\n\n![{correlation_output_file}]({correlation_output_file})"
    markdown_content += f"\n\n{narrative['correlation']}"

    outlierItems = outliersInfo['outlier_values']
    markdown_content += "\n\n### Outlier Detection \n\nBelow are the outlier details"
    table_header = "\n|Column  |(Min,Max) |\n|------|------|\n"
    table_rows = "\n".join([f"| {key} | {value} |" for key,value in outlierItems.items()])
    markdown_content += f"{table_header}{table_rows}"
    outliers_output_file = outliersInfo['output_file']
    markdown_content += f"\n\n![{outliers_output_file}]({outliers_output_file})"
    markdown_content += f"\n\n{narrative['outliers']}"

    markdown_content += "\n\n### K-Means Cluster \n\nBelow are the cluster details"
    table_header = "\n|Cluster  |Count  |\n|------|------|\n"
    table_rows = "\n".join([f"| {key} | {value} |" for key,value in clusterInfo['clusters'].items()])
    markdown_content += f"{table_header}{table_rows}"
    cluster_output_file = clusterInfo['output_file']
    markdown_content += f"\n\n![{cluster_output_file}]({cluster_output_file})"
    markdown_content += f"\n\n{narrative['cluster']}"

    for item in analysisSummary:
        markdown_content += f"\n\n### {item['title']} \n\nBelow is the analysis"
        markdown_content += f"\n\n![{item['output_file']}]({item['output_file']})"
        markdown_content += f"\n\n{item['insights']}"
        markdown_content += f"\n\n{item['recommendation']}"

    markdown_content += f"\n\n## Summary\n\n{narrative['summary']}"
    addContentToReadme(markdown_content, section)

def safe_format(value):
    '''
    Method to format numeric values or return 'N/A' for non-numeric/missing
    Args:
        value: int/float: value to be formatted
    Returns:
        str: formatted value
    '''
    return f"{value:.2f}" if pd.notna(value) and isinstance(value, (int, float)) else "N/A"

def addDescriptiveStatistics(statistics, summary, section = f"## Descriptive Statistics\n"):
    '''
    Method to add descriptive statistics to the README.md file
    Args:
        statistics: dict: descriptive statistics
        summary: str: summary of the statistics
        section: str: section to add the content
    '''
    markdown_table = "| Column | Count | Mean | Std | Min | 25% | 50% | 75% | Max | Null | Invalid |\n"
    markdown_table += "|--------|-------|------|-----|-----|-----|-----|-----|-----|------|---------|\n"
        
    for key in statistics.keys():
      stats = statistics[key]
      markdown_table += (f"| {key} | {safe_format(stats['count'])} | {safe_format(stats.get('mean'))} | {safe_format(stats.get('std'))} | {safe_format(stats.get('min'))} | {safe_format(stats.get('25%'))} | {safe_format(stats.get('50%'))} | {safe_format(stats.get('75%'))} | {safe_format(stats.get('max'))} |{safe_format(stats.get('null'))} |{safe_format(stats.get('invalid'))} |\n")

    addContentToReadme(markdown_table + "\n" + summary, section)

def getNumericalColumns(metadata):
    '''
    Method to get the numerical columns
    Args:
        metadata: list: metadata of the columns
    Returns:
        list: list of numerical columns
    '''
    return [entry['name'] for entry in metadata if ((entry['type'] in ['integer','float']) & entry['stats'])]

def addPreProcessingDetails(updated_values, clusterInfo, section = f"## Preprocessing\n"):
    '''
    Method to add preprocessing details to the README.md file
    Args:
        updated_values: dict: updated values after preprocessing
        section: str: section to add the content
    '''
    markdown_content = f"Rows dropped: {updated_values['dropped_rows']}\n\nBelow are count of values ignored due to out of range"
    table_header = "\n|Column  |Count  |\n|------|------|\n"
    table_rows = "\n".join([f"| {key} | {value} |" for key,value in updated_values['out_of_range_values'].items()])
    markdown_content += f"{table_header}{table_rows}"
    addContentToReadme(markdown_content, section)

def createReadMeFile(df, metadata, stats, updated_values, correlationInfo, outliersInfo, clusterInfo, summary, analysisSummary, narrative):
    '''
    Method to create the README.md file
    Args:
        df: DataFrame: dataframe to be analyzed
        metadata: list: metadata of the columns
        stats: dict: descriptive statistics
        updated_values: dict: updated values after preprocessing
        correlationInfo: dict: correlation information
        outliersInfo: dict: outliers information
        clusterInfo: dict: clusters information
        summary: dict: summary and next steps
        narrative: dict: narrative information
    '''
    addTitle(summary['title'])
    addIntroduction(summary['introduction'])
    addMetaData([{'name':col['name'], 'type':col['type'], 'description':col['description']} for col in metadata])
    addDescriptiveStatistics(stats, summary['summary'])
    addPreProcessingDetails(updated_values, clusterInfo)
    addAnalysisSection(correlationInfo, outliersInfo, clusterInfo, analysisSummary, narrative, "## Analysis\n")

def getInsightsFromImage(imageFile):
    '''
    Method to get insights from the image
    Args:
        imageFile: str: path to the image file
    Returns:
        str: inference, insights, recommendation
    '''
    response = handleRequest(CONCLUSION_PROMPT, imageFile, 'get_feedback')
    inference, insights, recommendation = json.loads(response['choices'][0]['message']['function_call']['arguments']).values()
    return inference, insights, recommendation

def getInsights(analysisSummary):
    '''
    Method to get insights from the analysis summary
    Args:
        analysisSummary: list: analysis summary
    Returns:
        list: analysis summary with insights
    '''
    for item in analysisSummary:
        inference, insights, recommendation = getInsightsFromImage(item['output_file'])
        item['inference'] = inference
        item['insights'] = insights
        item['recommendation'] = recommendation
    return analysisSummary

def analyseOutliers(df, featureInfo):
    '''
    Method to analyze the outliers in the dataframe and plot them in a single chart with normalized y-axis.
    Args:
        df: DataFrame: dataframe to be analyzed
        featureInfo: dict: feature information
    Returns:
        dict: outliers information
    '''
    # Extract numerical columns
    numerical_columns = [feature['name'] for feature in featureInfo if feature['stats']]
    df[numerical_columns] = df[numerical_columns].apply(pd.to_numeric, errors='coerce')

    # Compute z-scores
    z_scores = df[numerical_columns].apply(zscore)
    outliers = (z_scores.abs() > 3)
    
    # Initialize a single plot
    plt.figure(figsize=(12, 8))
    
    # Assign unique colors to each column
    palette = sns.color_palette("tab10", len(numerical_columns))
    
    # Loop through numerical columns and plot
    normalization_factors = {}
    for idx, col in enumerate(numerical_columns):
        # Normalize column values for better visibility
        normalization_factor = df[col].max() - df[col].min()
        normalization_factors[col] = normalization_factor
        normalized_values = df[col] / normalization_factor
        
        sns.scatterplot(
            x=df.index[outliers[col]],  # Only plot outliers
            y=normalized_values[outliers[col]],
            color=palette[idx],
            label=f"{col} (Norm Factor: {normalization_factor:.2f})"
        )
    output_file = "outliers_combined_normalized.png"
    # Add titles and labels
    plt.title("Outliers Across Numerical Columns (Normalized)")
    plt.xlabel("Index")
    plt.ylabel("Normalized Value")
    plt.legend(title="Columns (Normalization Factor)")
    plt.tight_layout()
    
    # Save the combined chart
    plt.savefig(output_file)
    plt.close()

    outlier_ranges = {}
    for col in numerical_columns:
        outlier_values = df[col][outliers[col]]
        if not outlier_values.empty:
            min_val, max_val = outlier_values.min(), outlier_values.max()
            outlier_ranges[col] = (min_val, max_val)
        else:
            outlier_ranges[col] = None  # No outliers found for this column
    
    return {"outliers":outliers, "outlier_values":outlier_ranges, "output_file":output_file}

def provideNarrative(df, statsInfo, updated_values, correlationInfo, outliersInfo, clusterInfo):
    '''
    Method to provide the narrative to the user
    Args:
        df: DataFrame: dataframe to be analyzed
        updated_values: dict: updated values after preprocessing
        correlationInfo: dict: correlation information
        outliersInfo: dict: outliers information
        clusterInfo: dict: clusters information
    '''
    content = f"Columns:{df.columns}\n\nData Types:{df.dtypes}\n\nstatistics: {statsInfo}\n\nUpdated Values: {updated_values}\n\nCorrelation: {correlationInfo['high_corr_matrix']}\n\nOutliers: {outliersInfo['outlier_values']}\n\nCluster: {clusterInfo['clusters']}"
    response = handleRequest("Provide the narrative", content, 'get_narrative')
    return json.loads(response['choices'][0]['message']['function_call']['arguments'])    

def analyse(fileName):
    try:
        df = loadFile(fileName)
        print("File loaded successfully")

        featureInfo = getFeatureInfo(df)
        print("Feature Info fetched successfully")

        statsInfo = getDescriptiveStats(df, featureInfo)
        print("Descriptive Stats populated successfully")

        df, updatedValues = dataPreprocessing(df,featureInfo, statsInfo)
        print("Preprocessing done successfully")

        correlationInfo = getHighCorrelation(df, featureInfo)
        print("Correlation done successfully")

        outliersInfo = analyseOutliers(df, featureInfo)
        print("Outliers analysis done successfully")

        summaryInfo = getSummaryAndNextSteps(df,statsInfo)
        print("Summary generation done successfully")

        clusterInfo = applyKMeansClustering(df, featureInfo)
        print("CLustering done successfully")

        analysisSummary = advancedAnalytics(df, statsInfo, summaryInfo)
        print("Analysis done successfully")

        analysisSummary = getInsights(analysisSummary)
        print("Generated insights successfully")

        narrative = provideNarrative(df, statsInfo, updatedValues, correlationInfo, outliersInfo, clusterInfo)
        print("Narrative generated successfully")

        #Add details to the README.md file
        createReadMeFile(df, featureInfo, statsInfo, updatedValues, correlationInfo, outliersInfo, clusterInfo, summaryInfo, analysisSummary, narrative)
        print("Output written to README.md")
    
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Please provide the file to be analyzed")
    else:
        analyse(sys.argv[1])

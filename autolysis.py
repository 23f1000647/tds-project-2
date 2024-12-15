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
#   "geopandas"
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
                            'requried':['column_name','column_type','description','stats']
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
    'get_prompts_for_analysis': [
        {
            'name':'get_prompts_for_analysis',
            'description':'Given the columns, data types and descriptive statistics, provide atleast 3 more unique prompts for further analysis',
            'parameters':{
                'type':'object',
                'properties':{
                    'prompts':{
                        'type':'array',
                        'description':'Unique prompts for further analysis',
                        'items':{
                            'type':'string',
                            'description': 'Prompt to request LLM for the given dataset to return code and export chart'
                        },
                        'minItems':3
                    }
                },
                'required':['prompts']
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
    # "Ensure the figure size does not exceed (5.12, 5.12) and set the dpi to a maximum of 100"
    "Do not display the chart; export it directly as a PNG file"
    "Use Seaborn for all plotting tasks"
)

ADVANCED_ANALYSIS_INSTRUCTION = (
    "Code should check for unique values of thr column being used analysis"
    "If this is greater than a certain threshold, then use sorting to find the top 10 values"
)

PROMPT_FOR_ANALYSIS_INSTRUCTION = (
    "Given the dataset's columns, data types, and descriptive statistics, provide at least three unique prompts for further analysis"
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
    try:
        with open(imagefile, 'rb') as file:
            image_data = file.read()
    except PermissionError as e:
        print(f"PermissionError: Ensure the file is not open elsewhere. {e}")
    except Exception as e:
        print(f"Error moving file: {e}")    
    return image_data

def createMessagePayload(instruction, userContent, imageFile):
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
        function: dict: function description dictionary
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
    print(response.json())
    return response.json()

def loadFile(fileName):
    '''
    Method to load the file
    '''
    try:
        encoding = getFileEncoding(fileName)
        df = pd.read_csv(fileName, encoding=encoding)
        return df
    except Exception as e:
        print(f"Error: {e}")

def getFeatureInfo(df):
    featureInfo = handleRequest(METADATA_INSTRUCTION, df[0:7].to_csv(index=False), 'get_column_dtypes')
    return json.loads(featureInfo['choices'][0]['message']['function_call']['arguments'])['column_metadata']

def getMinValue(featureInfo, columnName):
  for item in featureInfo:
    if item['name'] == columnName:
      return item['min_value']
    
def getDescriptiveStats(df, featureInfo):
    nullValues = df.isnull().sum().to_dict()
    columnForStats = [feature['name'] for feature in featureInfo if feature['stats']]
    descriptiveStats = df[columnForStats].describe().to_dict()
    for key, stats in descriptiveStats.items():
        if key in nullValues:
            stats['null'] = nullValues[key]
            stats['invalid'] = df[df[key] < getMinValue(featureInfo, key)].shape[0]
    return descriptiveStats

def dataPreprocessing(df,featureInfo, statsInfo):
    #Impute missing numeric values with mean
    imputer = SimpleImputer(missing_values=np.nan,strategy='mean')
    transformer = ColumnTransformer([('impute',imputer,list(statsInfo.keys()))
                                    ],remainder='passthrough',verbose_feature_names_out=False)
    df_imputed = transformer.fit_transform(df)
    df_imputed = pd.DataFrame(df_imputed,columns=transformer.get_feature_names_out())

    for col in df_imputed.columns:
      if col in statsInfo.keys():
        df_imputed.loc[df_imputed[col] < getMinValue(featureInfo, col), col] = np.nan

    df_imputed.dropna(inplace=True)
    return df_imputed

def getSummaryAndNextSteps(df,statsInfo):
    content = f"Columns:{df.columns}\n\nData Types:{df.dtypes}\n\nStatistics: {statsInfo}"
    response = handleRequest(INTRO_AND_DESCRIPTIVE_STATS_INSTRUCTION, content, 'get_intro_stats_summary')
    arguments = json.loads(response['choices'][0]['message']['function_call']['arguments'])
    return arguments

def getPromptsForAnalysis(df, statsInfo):
    content = f"Columns:{df.columns}\n\nData Types:{df.dtypes}\n\nStatistics: {statsInfo}"
    response = handleRequest(PROMPT_FOR_ANALYSIS_INSTRUCTION, content, 'get_prompts_for_analysis')
    return json.loads(response['choices'][0]['message']['function_call']['arguments'])['prompts']

def handleRequestAndExecute(instruction, content, functionName,df):
    response = handleRequest(instruction, content, functionName)
    codeBlock = ""
    error = ""
    attempt = 0
    flag = True
    while ((attempt < MAX_RETRY) & flag):
        try:
            if attempt > 0:
              content = f"code={codeBlock}\nerror={error}"
              response = handleRequest(instruction, content, functionName)
            codeBlock = json.loads(response['choices'][0]['message']['function_call']['arguments'])['python_code']
            output_file = json.loads(response['choices'][0]['message']['function_call']['arguments'])['output_file']
            rationale = json.loads(response['choices'][0]['message']['function_call']['arguments'])['rationale']            
            title = json.loads(response['choices'][0]['message']['function_call']['arguments'])['title']
            exec(codeBlock)
            flag = False
            return title, output_file, rationale
        except Exception as e:
            print(f"Exception message: {str(e)}")
            buffer = io.StringIO()
            traceback.print_exc(file=buffer)
            error = buffer.getvalue()
            print(f"Error: {error}")
            buffer.close()
        finally:
            attempt += 1

    return ""

def promptForAnalysis(df, statsInfo, summaryInfo):
    content = f"Columns:{df.columns}\n\nData Types:{df.dtypes}\n\nStatistics: {statsInfo}"

    analysis_output = []
    if summaryInfo["time_series"]["isavailable"]:
        try:
            prompt = GENERIC_CODE_INSTRUCTION + summaryInfo['time_series']['prompt']
            title, output_file, rationale = handleRequestAndExecute(prompt,content,"get_code_for_analysis",df)
            analysis_output.append({"title":title, "output_file":output_file, "rationale":rationale})
        except Exception as e:
            print(f"Error: {e}")

    if summaryInfo["geospatial"]["isavailable"]:
        try:
            prompt = GENERIC_CODE_INSTRUCTION + summaryInfo['geospatial']['prompt']
            title, output_file, rationale = handleRequestAndExecute(prompt,content,"get_code_for_analysis",df)
            analysis_output.append({"title":title, "output_file":output_file, "rationale":rationale})
        except Exception as e:
            print(f"Error: {e}")

    if summaryInfo["network"]["isavailable"]:
        try:
            prompt = GENERIC_CODE_INSTRUCTION + summaryInfo['network']['prompt']
            title, output_file, rationale = handleRequestAndExecute(prompt,content,"get_code_for_analysis",df)
            analysis_output.append({"title":title, "output_file":output_file, "rationale":rationale})
        except Exception as e:
            print(f"Error: {e}")

    if len(analysis_output) < 3:
        prompts = getPromptsForAnalysis(df, statsInfo)
        for prompt in prompts:
            try:
                prompt = GENERIC_CODE_INSTRUCTION + prompt
                title, output_file, rationale = handleRequestAndExecute(prompt, content, "get_code_for_analysis",df)
                analysis_output.append({"title":title, "output_file":output_file, "rationale":rationale})
            except Exception as e:
                print(f"Error: {e}")

    return analysis_output

def addContentToReadme(content, section = f"# Title\n"):
    '''
    Method to add content to the README.md file
    Args:
        file_path: str: path to the file
        content: str: content to be added
        section: str: section to add the content
    '''
    try:
      with open(OUTPUT_FILE, "a") as file:
          print(file.name)
          if section == f"# Title\n":
            file.write("# "+content+"\n")
          elif (section == f"## Summary\n"):
            if (content == ""):
              file.write(section)
            else:
              file.write(content+'\n')
          else:
            print(f"section:{section}, content={content}")
            file.write(section)
            file.write(content+'\n')
    except Exception as e:
      print("Error writing to ReadMe",e)

def addTitle(content, section = f"# Title\n"):
    '''
    Method to add title to the README.md file
    Args:
        file_path: str: path to the file
        content: str: title content
        section: str: section to add the content
    '''
    addContentToReadme(content, section)

def addIntroduction(content, section = f"## Introduction\n"):
    '''
    Method to add introduction to the README.md file
    Args:
        file_path: str: path to the file
        content: str: introduction content
        section: str: section to add the content
    '''
    addContentToReadme(content, section)

def addMetaData(content, section = f"## Metadata\n"):
    '''
    Method to add metadata section to the README.md file
    Args:
        file_path: str: path to the file
        content: list: metadata content
        section: str: section to add the content
    '''
    table_header = "\n|Name  |Type  |Description  |\n|------|------|-------------|\n"
    table_rows = "\n".join([f"| {item['name']} | {item['type']} | {item['description']} |" for item in content])
    markdown_content = f"{table_header}{table_rows}"
    addContentToReadme(markdown_content, section)

def addAnalysisSection(analysis,section=f"## Summary\n"):
    '''
    Method to add analysis section to the README.md file
    Args:
        file_path: str: path to the file
        section: str: section to add the content
    '''
    addTitle("", section)
    for item in analysis:
        addContentToReadme(f"### {item['title']}\n\n{item['rationale']}\n\n![{item['output_file']}]({item['output_file']})\n\n{item['inference']}\n\n{item['insights']}\n\n{item['recommendation']}", section)

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
        fileName: str: path to the file
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

def createReadMeFile(df, metadata, stats, summary, analysis):
    '''
    Method to create the README.md file
    Args:
        df: DataFrame: dataframe to be referred by code from LLM
        metadata: list: metadata of the columns
        stats: dict: descriptive statistics
        summary: dict: summary of the statistics
        analysis: list: analysis output
    '''
    addTitle(summary['title'])
    addIntroduction(summary['introduction'])
    addMetaData([{'name':col['name'], 'type':col['type'], 'description':col['description']} for col in metadata])
    addDescriptiveStatistics(stats, summary['summary'])
    addAnalysisSection(analysis, "## Summary\n")




def getInsightsFromImage(imageFile):
    response = handleRequest(CONCLUSION_PROMPT, imageFile, 'get_feedback')
    inference, insights, recommendation = json.loads(response['choices'][0]['message']['function_call']['arguments']).values()
    return inference, insights, recommendation

def getInsights(analysisSummary):
    for item in analysisSummary:
        inference, insights, recommendation = getInsightsFromImage(item['output_file'])
        item['inference'] = inference
        item['insights'] = insights
        item['recommendation'] = recommendation
    return analysisSummary


def analyse(fileName):
    try:
        df = loadFile(fileName)
        print("File loaded successfully")

        featureInfo = getFeatureInfo(df)
        print("Feature Info fetched successfully")

        statsInfo = getDescriptiveStats(df, featureInfo)
        print("Descriptive Stats populated successfully")

        df = dataPreprocessing(df,featureInfo, statsInfo)
        print("Preprocessing done successfully")

        summaryInfo = getSummaryAndNextSteps(df,statsInfo)
        print("Summary generation done successfully")

        analysisSummary = promptForAnalysis(df, statsInfo, summaryInfo)
        print("Analysis done successfully")

        analysisSummary = getInsights(analysisSummary)
        print("Generated insights successfully")

        #Add details to the README.md file
        createReadMeFile(df, featureInfo, statsInfo, summaryInfo, analysisSummary)
        print("Output written to README.md")
    
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Please provide the file to be analyzed")
    else:
        analyse(sys.argv[1])

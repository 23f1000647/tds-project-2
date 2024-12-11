# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "httpx",
#   "pandas",
#   "requests",
#   "numpy",
#   "seaborn",
#   "chardet",
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
            'name': 'get_intro_stats_summary',
            'description': 'Generate a title, introduction, and a brief summary of observations for a dataset as well as the next few prompts to ask LLM for further analysis',
            'parameters': {
                'type': 'object',
                'properties': {
                    'title': {
                        'type': 'string',
                        'description': (
                            'A concise and relevant title for the dataset based on its subject or purpose.'
                        )
                    },
                    'introduction': {
                        'type': 'string',
                        'description': (
                            'A short introduction providing an overview of the dataset, its structure, '
                            'and what it represents.'
                        )
                    },
                    'summary': {
                        'type': 'string',
                        'description': (
                            'Key observations and inferences from the provided descriptive statistics, '
                            'highlighting any significant patterns, trends, or anomalies.'
                        )
                    },
                    'next_analysis': {
                        'type': 'array',
                        'description': (
                            'Suggest types of analysis to perform on the dataset based on its characteristics. '
                            'Each analysis should be a string describing the type of analysis or visualization to perform.'
                        ),
                        'items': {
                            'type': 'string',
                            'description': "Best 3 prompts to ask LLM for further analysis"
                        },
                        'minItems': 3
                    }
                },
                'required': ['title', 'introduction', 'summary', 'next_analysis']
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
                    'rationale': {
                        'type': 'string',
                        'description': 'Provide rationale for choosing the analysis'
                    },
                    'inference': {
                        'type': 'string',
                        'description': 'Provide inference or insights based on the input image shared'
                    }
                },
                'required':['python_code','output_file','rationale','inference']
            }
        }
    ],
    'get_inference': [
        {
            'name':'get_inference',
            'description':'From the given image, provide the inference or insights based on the input image shared',
            'parameters':{
                'type':'object',
                'properties':{
                    'rationale': {
                        'type': 'string',
                        'description': 'Provide rationale for the response'
                    },
                    'inference': {
                        'type': 'string',
                        'description': 'Conclude with the inference or insights'
                    }
                },
                'required':['rationale','inference']
            }
        }
    ]
}

METADATA_INSTRUCTION = (
      'Analyze the initial lines of the provided dataset'
      'The first line represents the header, followed by a small portion of the data'
      'Extract the column names from the header and infer the data type for each column based on the values and their names' 
      'Estimate the minimum possible value for each column based on the column name'
      'Determine if the column is suitable for descriptive statistics (True/False) using the following guidelines: Numerical or continuous data is preferred,Identifiers or purely categorical data should not be considered,Consider the analytical value of data and relevance to potential use cases'
      'Data types should be determined from valid Python types, such as integer, float, datetime, string, boolean, or object'
      'Provide the results with clarity for further analysis'
)

INTRO_AND_DESCRIPTIVE_STATS_INSTRUCTION = (
    "Analyze the provided metadata and descriptive statistics of the dataset"
    "Suggest an appropriate, concise title for this analysis, relevant to the dataset's subject matter"
    "Write an introduction text summarizing the dataset, including its scope, purpose, and key attributes"
    "Provide a brief summary of observations drawn from the descriptive statistics, highlighting notable trends, outliers, and any data patterns that stand out"
    "Based on the dataset's metadata, descriptive statistics, and general characteristics:\nPropose the most suitable types of analysis to perform for this dataset.\nJustify the proposed analyses by explaining their relevance to the dataset's structure and potential insights.\nIf applicable, recommend specific techniques, statistical tests, or visualizations to explore further."
    "Output should also have next 3 prompts to be asked to LLM based on the dataset characteristics and statistics to generate relevant charts"
)

GENERIC_CODE_INSTRUCTION = (
    'Do not add any comments, return only python code'
    'Do not create dynamic charts (e.g., interactive plots, animations) that require user interaction'
    'Do not make your own synthetic data, dataset shall be available in dataframe named "df"'
    'Use the metadata and descriptive statistics provided as input for the exact column or feature names'
    'Generated python code should be error free and should be able to execute'
    'Limit figsize below within (5.12,5.12) and dpi within 100 '
    'Export the output chart if any generated for the prompt in png format'
    'Use seaborn for plotting'
)

CONCLUSION_PROMPT = (
    'Given the image, what do you infer from this'
    'Provide concluding text that best describe the image and the insights'
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


def requestLLM(instruction, userContent, functionName):
    '''
    Method to call LLM
    Args:
        instruction: str: instruction to be passed to LLM
        userContent: str: user content to be passed to LLM
        functionName: str: name of the function to be called
    Returns:
        dict: response from LLM in JSON format
    '''
    function_descriptions = getFunctionDescriptions(functionName)
    json_data = getPayload(instruction, userContent, functionName, function_descriptions)
    r = requests.post(AIPROXY_URL,headers=HEADERS,json=json_data)
    print(r.json())
    return r.json()

def getPayload(instruction, userContent, functionName, function):
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
    json_data={
        'model': MODEL,
        'messages': [
            {'role':'system','content':instruction},
            {'role':'user','content':userContent}
        ],
        'functions':function,
        'function_call': {'name':functionName}
    } 
    return json_data

def readImage(folderName, imagefile):
    try:
        imageToLoad = os.path.join(folderName, imagefile)
        with open(imageToLoad, 'rb') as file:
            image_data = file.read()
    except PermissionError as e:
        print(f"PermissionError: Ensure the file is not open elsewhere. {e}")
    except Exception as e:
        print(f"Error moving file: {e}")    
    return image_data

def getPayloadForImage(instruction, folderName, imagefile, functionName, function):
    '''
    Method to get the payload to be passed to LLM
    Args:
        instruction: str: instruction to be passed to LLM
        imagefile: str: file name of image to be loaded and passed to LLM
        functionName: str: name of the function to be called
        function: dict: function description dictionary
    Returns:
        dict: payload to be passed to LLM
    '''
    image_data = readImage(folderName, imagefile)
    mime_type = "image/png" if imagefile.endswith(".png") else "image/jpeg"
    base64_image = base64.b64encode(image_data).decode('utf-8')
    image_url = f"data:{mime_type};base64,{base64_image}"

    base64_image = base64.b64encode(image_data).decode('utf-8')
    json_data={
        'model': MODEL,
        'messages': [
            {
                'role':'user',
                'content': [
                    {'type':'text','text':instruction},
                    {'type':'image_url','image_url':{'detail':'low','url':image_url}}
                ]
            },
        ],
        'functions':function,
        'function_call': {'name':functionName}
    } 
    return json_data

def retryRequest(instruction, code, error, functionName):
    '''
    Method to retry the request
    Args:
        code: str: code block to be executed
        error: str: error message
    Returns:
        requests.Response: response from LLM
    '''
    function_descriptions = FUNCTIONS_DESCRIPTIONS_DICT[functionName]
    code_and_error = "code="+json.dumps(code) + "\n"+"error="+error
    print(code_and_error)
    json_data = getPayload(instruction, code_and_error, functionName, function_descriptions)
    return requests.post(AIPROXY_URL,headers=HEADERS,json=json_data)


def requestAndExecuteLLM(instruction, userContent, functionName,df,folderName,fileName):
    '''
    Method to request LLM and execute the code block
    Args:
        instruction: str: instruction to be passed to LLM
        userContent: str: user content to be passed to LLM
        functionName: str: name of the function to be called
    '''
    function_descriptions = FUNCTIONS_DESCRIPTIONS_DICT[functionName]
    json_data = getPayload(instruction, userContent, functionName,function_descriptions)
    r = requests.post(AIPROXY_URL,headers=HEADERS,json=json_data)
    attempt = 0
    flag = True
    while ((attempt < MAX_RETRY) & flag):
        try:
            if attempt > 0:
              r = retryRequest(instruction, codeBlock, error, functionName)
            print(r.json())
            codeBlock = json.loads(r.json()['choices'][0]['message']['function_call']['arguments'])['python_code']
            exec(codeBlock)
            output_file = json.loads(r.json()['choices'][0]['message']['function_call']['arguments'])['output_file']
            saveChart(output_file,folderName)
            rationale = json.loads(r.json()['choices'][0]['message']['function_call']['arguments'])['rationale']
            flag = False
            return (output_file, rationale)
        except Exception as e:
            buffer = io.StringIO()
            traceback.print_exc(file=buffer)
            error = buffer.getvalue()
            print(f"Error: {error}")
            buffer.close()
        finally:
            attempt += 1
    return

def requestInferenceForImageData(instruction, imageFile, functionName, folderName,fileName):
    '''
    Method to request LLM and execute the code block
    Args:
        instruction: str: instruction to be passed to LLM
        userContent: str: user content to be passed to LLM
        functionName: str: name of the function to be called
    '''
    function_descriptions = FUNCTIONS_DESCRIPTIONS_DICT[functionName]
    json_data = getPayloadForImage(instruction, folderName, imageFile, functionName, function_descriptions)
    r = requests.post(AIPROXY_URL,headers=HEADERS,json=json_data)
    print(r.json())
    rationale = json.loads(r.json()['choices'][0]['message']['function_call']['arguments'])['rationale']
    inference = json.loads(r.json()['choices'][0]['message']['function_call']['arguments'])['inference']
    return (rationale, inference)

def saveChart(output_file,folder_name):
    '''
    Method to save the chart to a file
    Args:
        chart: object: chart object
        output_file: str: path to the output file
    '''
    if os.path.exists(output_file):
        try:
            # Rename or move the file
            os.rename(output_file, os.path.join(folder_name, output_file))
            print(f"File moved to {folder_name} successfully.")
        except PermissionError as e:
            print(f"PermissionError: Ensure the file is not open elsewhere. {e}")
        except Exception as e:
            print(f"Error moving file: {e}")                


def addContentToReadme(filePath, content, section = f"# Title\n"):
    '''
    Method to add content to the README.md file
    Args:
        file_path: str: path to the file
        content: str: content to be added
        section: str: section to add the content
    '''
    try:
      with open(filePath, "a") as file:
          print(file.name)
          if section == f"# Title\n":
            file.write("# "+content+"\n")
          else:
            file.write(section)
            file.write(content+'\n')
    except Exception as e:
      print("Error writing to ReadMe",e)

def addTitle(filePath, content, section = f"# Title\n"):
    '''
    Method to add title to the README.md file
    Args:
        file_path: str: path to the file
        content: str: title content
        section: str: section to add the content
    '''
    addContentToReadme(filePath, content, section)

def addIntroduction(filePath, content, section = f"## Introduction\n"):
    '''
    Method to add introduction to the README.md file
    Args:
        file_path: str: path to the file
        content: str: introduction content
        section: str: section to add the content
    '''
    addContentToReadme(filePath, content, section)

def addMetaData(filePath, content, section = f"## Metadata\n"):
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
    addContentToReadme(filePath, markdown_content, section)

def addAnalysisSection(file_path,section=f"## Summary\n"):
    '''
    Method to add analysis section to the README.md file
    Args:
        file_path: str: path to the file
    '''
    addContentToReadme(file_path, "", section)

def addAnalysis(file_path, image_file, content, section=f"### Obervation 1\n"):
    '''
    Method to add analysis to the README.md file
    Args:
        file_path: str: path to the file
        image_file: str: path to the image file
        rationale: str: rationale for the analysis
    '''
    addContentToReadme(file_path, f"{content}\n\n![{image_file}]({image_file})\n", section)

def safe_format(value):
    '''
    Method to format numeric values or return 'N/A' for non-numeric/missing
    Args:
        value: int/float: value to be formatted
    Returns:
        str: formatted value
    '''
    return f"{value:.2f}" if pd.notna(value) and isinstance(value, (int, float)) else "N/A"

def addDescriptiveStatistics(fileName, statistics, summary, section = f"## Descriptive Statistics\n"):
    '''
    Method to add descriptive statistics to the README.md file
    Args:
        file_path: str: path to the file
        desc_stats: dict: descriptive statistics
        content: list: metadata content
        section: str: section to add the content
    '''
    markdown_table = "| Column | Count | Mean | Std | Min | 25% | 50% | 75% | Max |\n"
    markdown_table += "|--------|-------|------|-----|-----|-----|-----|-----|-----|\n"
        
    for index in statistics.index:
      stats = statistics.loc[index]
      markdown_table += (f"| {index} | {safe_format(stats['count'])} | {safe_format(stats.get('mean'))} | {safe_format(stats.get('std'))} | {safe_format(stats.get('min'))} | {safe_format(stats.get('25%'))} | {safe_format(stats.get('50%'))} | {safe_format(stats.get('75%'))} | {safe_format(stats.get('max'))} |\n")

    addContentToReadme(fileName, markdown_table + "\n" + summary, section)

def getMetadata(instruction, data, functionName):
    '''
    Method to get the introduction and metadata
    Args:
        instruction: str: instruction to be passed to LLM
        data: str: data to be passed to LLM
        functionName: str: name of the function to be called
    Returns:
        dict: response from LLM
    '''
    response = requestLLM(instruction, data, functionName)
    print(response)
    return json.loads(response['choices'][0]['message']['function_call']['arguments'])['column_metadata']

def getNumericalColumns(metadata):
    '''
    Method to get the numerical columns
    Args:
        metadata: list: metadata of the columns
    Returns:
        list: list of numerical columns
    '''
    return [entry['name'] for entry in metadata if ((entry['type'] in ['integer','float']) & entry['stats'])]

def getIntroAndSummary(instruction, data, functionName):
    '''
    Method to get the introduction and metadata
    Args:
        instruction: str: instruction to be passed to LLM
        data: str: data to be passed to LLM
        functionName: str: name of the function to be called
    Returns:
        dict: response from LLM
    '''
    response = requestLLM(instruction, data, functionName)
    return json.loads(response['choices'][0]['message']['function_call']['arguments'])

def loadFileAndAnalyze(fileName):
    '''
    Method to load the file and analyze it
    Args:
        fileName: str: path to the file
    '''
    folderName = fileName[:-4]
    os.makedirs(folderName, exist_ok=True)
    file_path = os.path.join(folderName, OUTPUT_FILE)
    encoding = getFileEncoding(fileName)
    df = pd.read_csv(fileName, encoding=encoding)
    metadata = getMetadata(METADATA_INSTRUCTION, df[0:10].to_csv(index=False), 'get_column_dtypes')
    introsummaryresponse = getIntroAndSummary(INTRO_AND_DESCRIPTIVE_STATS_INSTRUCTION, json.dumps(metadata), 'get_intro_stats_summary')
    print(introsummaryresponse)
    addTitle(file_path, introsummaryresponse['title'])
    addIntroduction(file_path, introsummaryresponse['introduction'])
    addMetaData(file_path, [{'name':col['name'], 'type':col['type'], 'description':col['description']} for col in metadata])
    addDescriptiveStatistics(file_path, df[getNumericalColumns(metadata)].describe().transpose(), introsummaryresponse['summary'])
    addAnalysisSection(file_path, "## Analysis\n")
    for part in range(len(introsummaryresponse['next_analysis'])):
        prompt = introsummaryresponse['next_analysis'][part]
        image_file, rationale = requestAndExecuteLLM(GENERIC_CODE_INSTRUCTION + prompt, json.dumps(metadata), 'get_code_for_analysis',df,folderName,file_path)
        print(f"Output file: {image_file}, rationale: {rationale}")
        rationale, inference = requestInferenceForImageData(CONCLUSION_PROMPT, image_file, 'get_inference',folderName,file_path)
        print(f"rationale: {rationale}, inference: {inference}")
        addAnalysis(file_path, image_file, rationale + inference, "### Observation "+str(part+1)+"\n")


if __name__ == "__main__":
    loadFileAndAnalyze(sys.argv[1])

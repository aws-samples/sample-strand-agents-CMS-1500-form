import logging
from typing import List, Dict
import pandas as pd
import json
from strands import Agent, tool
from strands.models import BedrockModel
import os


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
)
logger = logging.getLogger('insurance_processor')

@tool
def read_excel_schema(schema_path: str) -> List[str]:
    """
    Read the Excel schema file and return the list of field names. NOTE - a single patient may have multiple insurance company benefits, plans, policies - in some cases more than 9. NOTE - it is rare to have BOTH patient AND subscriber data in a patient's coverage - by default the patient is the subscriber if only ONE
    
    Args:
        schema_path (str): Path to the Excel schema file
        
    Returns:
        List[str]: List of field names from the schema
    """
    try:
        df = pd.read_excel(schema_path)
        fields = df['Schema Field'].tolist()
        logger.info(f"Successfully read schema with {len(fields)} fields")
        return fields
    except Exception as e:
        logger.error(f"Error reading schema: {str(e)}")
        raise

@tool
def read_json_data(json_path: str) -> Dict:
    """
    Read the JSON file containing patient data.
    
    Args:
        json_path (str): Path to the JSON file
        
    Returns:
        Dict: JSON data as a dictionary
    """
    try:
        with open(json_path, 'r') as f:
            data = json.load(f)
        logger.info("Successfully read JSON data")
        return data
    except Exception as e:
        logger.error(f"Error reading JSON data: {str(e)}")
        raise

@tool
def process_insurance_data(schema_fields: List[str], json_data: Dict) -> List[Dict]:
    """
    Process insurance plans data according to the schema.
    
    Args:
        schema_fields (List[str]): List of field names from the schema
        json_data (Dict): JSON data containing insurance information
        
    Returns:
        List[Dict]: List of processed insurance plan rows
    """
    rows = []
    payers = json_data.get('payers', [])
    
    for idx, payer in enumerate(payers, 1):
        row = {}
        
        # Initialize all fields to empty string first
        for field in schema_fields:
            row[field] = ''
        
        # Handle basic payer fields
        if 'patient_insurance_id' in row:
            # Try to get coverageId from the payer, or from the root level if specified
            coverage_id = payer.get('coverageId', '')
            if not coverage_id and 'coverageId' in json_data:
                coverage_id = json_data.get('coverageId', '')
            row['patient_insurance_id'] = str(coverage_id)
        if 'payer_name' in row:
            row['payer_name'] = payer['issuer'].get('issuerName', '') if 'issuer' in payer else ''
        if 'rank' in row:
            row['rank'] = payer.get('payerRank', '')
        if 'type' in row:
            row['type'] = payer.get('payPlanType', '')
        if 'medicare' in row:
            pay_plan_type = payer.get('payPlanType', '').lower()
            row['medicare'] = payer.get('accountNumber', '') if 'medicare' in pay_plan_type else ''
        if 'medicaid' in row:
            pay_plan_type = payer.get('payPlanType', '').lower()
            row['medicaid'] = payer.get('accountNumber', '') if 'medicaid' in pay_plan_type else ''
        if 'patient_member_id' in row:
            row['patient_member_id'] = payer.get('accountNumber', '')
        
        # Handle insuredParty fields
        if 'insuredParty' in payer:
            insured = payer['insuredParty']
            if 'patient_first_name' in row:
                row['patient_first_name'] = insured.get('firstName', '')
            if 'patient_last_name' in row:
                row['patient_last_name'] = insured.get('lastName', '')
            if 'patient_middle_name' in row:
                row['patient_middle_name'] = insured.get('middleName', '')
            if 'patient_dob' in row:
                row['patient_dob'] = insured.get('birthDate', '')
            if 'patient_gender' in row:
                row['patient_gender'] = insured.get('gender', '')
            if 'patient_ssn' in row:
                row['patient_ssn'] = insured.get('socialBeneficiaryIdentifier', '')
            if 'relation' in row:
                row['relation'] = insured.get('relationship', '')
            
            # Handle address fields
            if 'address' in insured:
                address = insured['address']
                if 'patient_address' in row:
                    row['patient_address'] = address.get('addressLine1', '')
                if 'patient_city' in row:
                    row['patient_city'] = address.get('city', '')
                if 'patient_state' in row:
                    row['patient_state'] = address.get('state', '')
                if 'patient_zip' in row:
                    row['patient_zip'] = address.get('postalCode', '')
        
        # Handle issuer fields
        if 'issuer' in payer:
            issuer = payer['issuer']
            if 'group_name' in row:
                row['group_name'] = issuer.get('groupName', '')
            if 'group_number' in row:
                row['group_number'] = str(issuer.get('group', ''))
            if 'plan_number' in row:
                row['plan_number'] = issuer.get('planNumber', '')
            if 'policy_StartDate' in row:
                row['policy_StartDate'] = issuer.get('planEffectiveDate', '')
            if 'policy_EndDate' in row:
                row['policy_EndDate'] = issuer.get('planExpirationDate', '')
                
        rows.append(row)
    
    return rows

@tool
def write_csv_output(output_path: str, schema_fields: List[str], rows: List[Dict]) -> bool:
    """
    Write the processed data to a CSV file.
    
    Args:
        output_path (str): Path where the CSV file should be written
        schema_fields (List[str]): List of field names for CSV headers
        rows (List[Dict]): List of rows to write to CSV
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        df = pd.DataFrame(rows)
        # Ensure columns are in the same order as schema
        df = df.reindex(columns=schema_fields)
        df.to_csv(output_path, index=False)
        logger.info(f"Successfully wrote {len(rows)} rows to CSV")
        return True
    except Exception as e:
        logger.error(f"Error writing CSV: {str(e)}")
        return False

def create_insurance_agent():
    """Create and configure the Strands Agent for insurance processing."""
    # Create a BedrockModel with custom configuration
    bedrock_model = BedrockModel(
        #model_id="us.anthropic.claude-3-5-sonnet-20240620-v1:0",
        model_id="us.meta.llama4-scout-17b-instruct-v1:0",
        #model_id="us.amazon.nova-premier-v1:0",
        region_name='us-east-1',
        client_args={
            'config': {
                'read_timeout': 300,  # 5 minutes timeout
                'connect_timeout': 300,
                'max_pool_connections': 10
            }
        }
    )
    
    # Create the agent with our custom tools
    agent = Agent(
        model=bedrock_model,
        tools=[read_excel_schema, read_json_data, process_insurance_data, write_csv_output],
        system_prompt="""You are an insurance data processing assistant. Your role is to help process 
        insurance data from JSON files according to specified schemas and generate CSV output files. 
        You should use the provided tools to:
        1. Read the schema from Excel
        2. Read the insurance data from JSON
        3. Process the data according to the schema
        4. Generate the CSV output
        
        Always verify the data processing steps and ensure accurate mapping of fields."""
    )
    return agent

def process_insurance_files():
    """Process insurance files directly without agent interaction."""
    # File paths
    SCHEMA_PATH = '/home/sagemaker-user/Strand-PCC/golden-schema-v2.xlsx'
    JSON_PATH = '/home/sagemaker-user/Strand-PCC/anonymized-patient-data.json'
    OUTPUT_PATH = '/home/sagemaker-user/Strand-PCC/llama4-insurance_plans_output.csv'
    
    try:
        # Step 1: Read schema
        print("Step 1: Reading schema...")
        schema_fields = read_excel_schema(SCHEMA_PATH)
        print(f"Successfully read {len(schema_fields)} schema fields")
        
        # Step 2: Read JSON data
        print("Step 2: Reading JSON data...")
        json_data = read_json_data(JSON_PATH)
        print("Successfully read JSON data")
        
        # Step 3: Process insurance data
        print("Step 3: Processing insurance data...")
        processed_rows = process_insurance_data(schema_fields, json_data)
        print(f"Successfully processed {len(processed_rows)} insurance records")
        
        # Step 4: Write CSV output
        print("Step 4: Writing CSV output...")
        success = write_csv_output(OUTPUT_PATH, schema_fields, processed_rows)
        
        if success:
            print(f"Successfully completed processing. Output written to: {OUTPUT_PATH}")
        else:
            print("Failed to write CSV output")
            
    except Exception as e:
        print(f"Error during processing: {str(e)}")
        logger.error(f"Processing failed: {str(e)}")

if __name__ == "__main__":
    # Process files directly
    process_insurance_files()
    
    # Optionally, you can still use the agent for interactive queries
    # Uncomment the following lines if you want to use the agent interactively
    """
    # Create the agent
    agent = create_insurance_agent()
    
    # Process the insurance data
    message = '''Please help me understand the insurance data processing. The files have been processed directly, 
    but I may need help with analysis or modifications.'''
    
    # Run the agent
    result = agent(message)
    print(result.message)
    """

"""
AWS Strands Agent Client
Handles all communication with the AWS Strands Agent runtime
"""
import boto3
import json
import os
from typing import Dict, Any, Optional
from botocore.exceptions import ClientError

class StrandsAgentClient:
    def __init__(self):
        """Initialize the Strands Agent client with AWS credentials"""
        self.aws_region = os.getenv('AWS_REGION', 'us-east-1')
        self.agent_id = os.getenv('AWS_STRANDS_AGENT_ID')
        self.agent_alias_id = os.getenv('AWS_STRANDS_AGENT_ALIAS_ID', 'TSTALIASID')
        
        # Initialize boto3 client for Bedrock Agent Runtime
        try:
            self.client = boto3.client(
                'bedrock-agent-runtime',
                region_name=self.aws_region,
                aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
                aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')
            )
        except Exception as e:
            print(f"Warning: Could not initialize AWS client: {e}")
            self.client = None
    
    def invoke_agent(self, prompt: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Invoke the Strands Agent with a formatted prompt
        
        Args:
            prompt: The formatted prompt to send to the agent
            session_id: Optional session ID for maintaining conversation context
            
        Returns:
            Dict containing the agent's response and metadata
        """
        if not self.client or not self.agent_id:
            # Fallback response when AWS is not configured
            return {
                "success": False,
                "message": "AWS Strands Agent not configured",
                "insights": "Agent integration requires AWS credentials configuration.",
                "recommendations": []
            }
        
        try:
            # Generate session ID if not provided
            if not session_id:
                import uuid
                session_id = str(uuid.uuid4())
            
            # Invoke the agent
            response = self.client.invoke_agent(
                agentId=self.agent_id,
                agentAliasId=self.agent_alias_id,
                sessionId=session_id,
                inputText=prompt
            )
            
            # Process the streaming response
            completion_text = ""
            for event in response.get('completion', []):
                if 'chunk' in event:
                    chunk = event['chunk']
                    if 'bytes' in chunk:
                        completion_text += chunk['bytes'].decode('utf-8')
            
            return {
                "success": True,
                "insights": completion_text,
                "session_id": session_id,
                "agent_id": self.agent_id
            }
            
        except ClientError as e:
            error_message = str(e)
            print(f"AWS Strands Agent error: {error_message}")
            return {
                "success": False,
                "error": error_message,
                "insights": f"Agent invocation failed: {error_message}"
            }
        except Exception as e:
            error_message = str(e)
            print(f"Unexpected error invoking agent: {error_message}")
            return {
                "success": False,
                "error": error_message,
                "insights": f"Unexpected error: {error_message}"
            }
    
    def is_configured(self) -> bool:
        """Check if the agent client is properly configured"""
        return self.client is not None and self.agent_id is not None

"""
Agent Logic Module
Defines how backend data is converted into agent prompts and processes responses
"""
from typing import Dict, Any, List
import json

class AgentLogic:
    @staticmethod
    def format_alerts_prompt(alerts: List[Dict[str, Any]]) -> str:
        """
        Convert alerts data into a structured prompt for the agent
        
        Args:
            alerts: List of alert dictionaries
            
        Returns:
            Formatted prompt string
        """
        alert_summary = []
        for alert in alerts:
            alert_summary.append({
                "id": alert.get("id"),
                "title": alert.get("title"),
                "severity": alert.get("severity"),
                "source": alert.get("source"),
                "message": alert.get("message"),
                "resources": alert.get("affected_resources", [])
            })
        
        prompt = f"""Analyze the following cloud infrastructure alerts and provide:
1. Severity classification and priority ranking
2. Quick action summary for each alert
3. Potential root causes
4. Recommended immediate actions

Alerts data:
{json.dumps(alert_summary, indent=2)}

Provide a structured analysis with clear recommendations."""
        
        return prompt
    
    @staticmethod
    def format_resources_prompt(resources: List[Dict[str, Any]]) -> str:
        """
        Convert resources data into a structured prompt for the agent
        
        Args:
            resources: List of resource dictionaries
            
        Returns:
            Formatted prompt string
        """
        resource_summary = []
        for resource in resources:
            resource_summary.append({
                "id": resource.get("id"),
                "name": resource.get("name"),
                "type": resource.get("type"),
                "status": resource.get("status"),
                "utilization": resource.get("utilization"),
                "monthly_cost": resource.get("monthly_cost"),
                "region": resource.get("region")
            })
        
        prompt = f"""Analyze the following cloud resources and provide:
1. Cost-saving opportunities and rightsizing recommendations
2. Utilization analysis and optimization strategies
3. Regional optimization suggestions
4. Estimated cost savings for each recommendation

Resources data:
{json.dumps(resource_summary, indent=2)}

Provide specific, actionable recommendations with estimated cost impact."""
        
        return prompt
    
    @staticmethod
    def format_security_prompt(findings: List[Dict[str, Any]]) -> str:
        """
        Convert security findings into a structured prompt for the agent
        
        Args:
            findings: List of security finding dictionaries
            
        Returns:
            Formatted prompt string
        """
        findings_summary = []
        for finding in findings:
            findings_summary.append({
                "id": finding.get("id"),
                "title": finding.get("title"),
                "severity": finding.get("severity"),
                "description": finding.get("description"),
                "compliance": finding.get("compliance", []),
                "resource": finding.get("resource")
            })
        
        prompt = f"""Analyze the following security findings and provide:
1. Risk impact assessment for each finding
2. Compliance mapping (SOC2, ISO 27001, GDPR)
3. Prioritization based on risk severity and business impact
4. Remediation steps and estimated effort

Security findings:
{json.dumps(findings_summary, indent=2)}

Provide a comprehensive security analysis with clear remediation roadmap."""
        
        return prompt
    
    @staticmethod
    def format_optimization_prompt(data: Dict[str, Any]) -> str:
        """
        Convert optimization data into a structured prompt for the agent
        
        Args:
            data: Optimization data dictionary
            
        Returns:
            Formatted prompt string
        """
        prompt = f"""Analyze the following cloud optimization opportunities and provide:
1. Multi-factor recommendations combining cost, performance, and sustainability
2. Priority ranking based on potential impact
3. Implementation complexity assessment
4. Expected ROI and timeline

Optimization data:
{json.dumps(data, indent=2)}

Provide a strategic optimization roadmap with clear action items."""
        
        return prompt
    
    @staticmethod
    def process_agent_response(response: Dict[str, Any], data_type: str) -> Dict[str, Any]:
        """
        Process and structure the agent's response based on data type
        
        Args:
            response: Raw response from the agent
            data_type: Type of data (alerts, resources, security, optimization)
            
        Returns:
            Structured response dictionary
        """
        if not response.get("success"):
            return {
                "agent_enabled": False,
                "error": response.get("error", "Agent invocation failed"),
                "insights": response.get("insights", "No insights available")
            }
        
        # Extract insights from the response
        insights = response.get("insights", "")
        
        # Structure the response based on data type
        structured_response = {
            "agent_enabled": True,
            "insights": insights,
            "data_type": data_type,
            "session_id": response.get("session_id"),
            "recommendations": AgentLogic._extract_recommendations(insights)
        }
        
        return structured_response
    
    @staticmethod
    def _extract_recommendations(insights_text: str) -> List[str]:
        """
        Extract key recommendations from the insights text
        
        Args:
            insights_text: The full insights text from the agent
            
        Returns:
            List of key recommendations
        """
        # Simple extraction - look for numbered lists or bullet points
        recommendations = []
        lines = insights_text.split('\n')
        
        for line in lines:
            line = line.strip()
            # Look for numbered items or bullet points
            if line and (line[0].isdigit() or line.startswith('-') or line.startswith('•')):
                # Clean up the line
                cleaned = line.lstrip('0123456789.-•) ').strip()
                if cleaned and len(cleaned) > 10:  # Avoid very short lines
                    recommendations.append(cleaned)
        
        return recommendations[:10]  # Return top 10 recommendations

# AWS Strands Agent Integration

This module handles all communication with AWS Strands Agent for AI-driven cloud infrastructure insights.

## Architecture

```
┌─────────────────┐
│  FastAPI Route  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  agent_logic.py │  ← Formats prompts, processes responses
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ agent_client.py │  ← Communicates with AWS Bedrock Agent Runtime
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  AWS Strands    │
│     Agent       │
└─────────────────┘
```

## Components

### `agent_client.py`
Handles low-level AWS SDK communication:
- Initializes boto3 client for Bedrock Agent Runtime
- Manages authentication and session handling
- Processes streaming responses from the agent
- Handles errors and provides fallback responses

### `agent_logic.py`
Converts backend data into structured prompts:
- **Alerts**: Formats alert data for severity classification and priority ranking
- **Resources**: Creates prompts for cost optimization and rightsizing analysis
- **Security**: Structures security findings for risk assessment and compliance mapping
- **Optimization**: Combines multi-factor data for strategic recommendations

## Usage

### Basic Integration
```python
from agent_integration.agent_client import StrandsAgentClient
from agent_integration.agent_logic import AgentLogic

# Initialize
client = StrandsAgentClient()
logic = AgentLogic()

# Process data through agent
prompt = logic.format_alerts_prompt(alerts_data)
response = client.invoke_agent(prompt)
insights = logic.process_agent_response(response, "alerts")
```

### API Endpoint Pattern
```python
@app.get("/endpoint")
def endpoint(use_agent: bool = Query(False)):
    data = get_data()
    
    if use_agent and agent_client.is_configured():
        prompt = agent_logic.format_prompt(data)
        agent_response = agent_client.invoke_agent(prompt)
        processed = agent_logic.process_agent_response(agent_response, "type")
        
        return {
            "data": data,
            "agent_insights": processed
        }
    
    return data
```

## Agent Outputs

### Alerts Analysis
- Severity classification (Critical/High/Medium/Low)
- Priority ranking based on business impact
- Quick action summaries
- Root cause identification

### Resources Optimization
- Cost-saving opportunities with dollar estimates
- Rightsizing recommendations (instance types, sizes)
- Utilization analysis and trends
- Regional optimization suggestions

### Security Assessment
- Risk impact scores
- Compliance mapping (SOC2, ISO 27001, GDPR, HIPAA)
- Remediation priority matrix
- Estimated remediation effort

### Multi-Factor Optimization
- Combined cost + performance + sustainability analysis
- Strategic roadmap with timelines
- ROI projections
- Implementation complexity ratings

## Configuration

Required environment variables:
```bash
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
AWS_STRANDS_AGENT_ID=agent_id
AWS_STRANDS_AGENT_ALIAS_ID=TSTALIASID
```

## Error Handling

The module provides graceful fallbacks:
- Missing AWS credentials → Returns mock data
- Agent invocation failure → Returns error with details
- Network issues → Logs error, returns fallback response
- Partial responses → Handles streaming interruptions

## Cost Management

Estimated costs (< $100/month for typical usage):
- **Bedrock Agent Runtime**: ~$0.0003 per request
- **Data transfer**: Minimal (< 1GB/month)
- **CloudWatch Logs**: ~$0.50/GB ingested
- **DynamoDB** (optional): Free tier eligible

### Cost Optimization Tips
1. Cache frequently requested insights (5-15 min TTL)
2. Batch similar requests when possible
3. Use shorter prompts for simple queries
4. Implement request throttling during off-hours
5. Monitor usage via CloudWatch metrics

## Testing

Test without AWS configuration:
```python
# Agent will return fallback responses
response = client.invoke_agent("test prompt")
assert response["success"] == False
assert "not configured" in response["message"]
```

Test with mock AWS client:
```python
from unittest.mock import MagicMock

client.client = MagicMock()
client.agent_id = "test-agent-id"
# Test invocation logic
```

## Future Enhancements

Potential additions:
- [ ] DynamoDB integration for prompt/response caching
- [ ] Lambda functions for batch processing
- [ ] Multi-agent orchestration for complex workflows
- [ ] Custom knowledge bases for domain-specific insights
- [ ] Integration with AWS Cost Explorer for real-time cost data
- [ ] Streaming responses to frontend via WebSocket
- [ ] Agent memory persistence across sessions

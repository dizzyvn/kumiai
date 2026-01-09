---
name: Data Analysis & Notifications
description: Analyze data and send notifications to external services
allowed-tools: Read, Write, Grep
allowed-mcp-servers: gmail
allowed-custom-tools:
  - python__math__calculate_metrics
  - python__utils__text_transform
  - http__slack__notification
  - http__api__call
icon: chart-bar
iconColor: "#10B981"
---

# Data Analysis & Notifications Skill

This skill demonstrates how to combine:
- **Built-in tools** (Read, Write, Grep)
- **MCP servers** (gmail)
- **Custom Python tools** (python__math__, python__utils__)
- **Custom HTTP tools** (http__slack__, http__api__)

## Capabilities

### Data Processing
- Read and parse data files
- Calculate statistics (sum, mean, min, max)
- Transform text (uppercase, lowercase, reverse)

### External Communication
- Send email via Gmail MCP server
- Send Slack notifications
- Call custom REST APIs

## Example Usage

### 1. Analyze CSV data and send results to Slack

```
Agent can:
1. Use Read tool to load data.csv
2. Parse numbers from file
3. Use python__math__calculate_metrics to get statistics
4. Use http__slack__notification to send results to #analytics channel
```

### 2. Process text files and email summary

```
Agent can:
1. Use Grep to search for patterns in logs
2. Use python__utils__text_transform to format results
3. Use mcp__gmail__send_email to email summary
```

### 3. Monitor API and alert on changes

```
Agent can:
1. Use http__api__call to fetch data from external API
2. Compare with previous state (stored in file via Write)
3. Use http__slack__notification to alert team if changed
```

## Tool Reference

### Python Tools (In-process, fast)

**python__math__calculate_metrics**
```json
{
  "numbers": [1, 2, 3, 4, 5]
}
```
Returns: sum, mean, min, max, count

**python__utils__text_transform**
```json
{
  "text": "hello world",
  "operation": "uppercase"
}
```
Returns: {"result": "HELLO WORLD"}

### HTTP Tools (External APIs)

**http__slack__notification**
```json
{
  "body": {
    "text": "Analysis complete! Mean: 42.5",
    "channel": "#analytics"
  }
}
```

**http__api__call** (Generic)
```json
{
  "url": "https://api.example.com/data",
  "method": "GET",
  "headers": {"Authorization": "Bearer TOKEN"}
}
```

## Best Practices

1. **Use Python tools for**:
   - Data transformations
   - Calculations
   - Business logic
   - Performance-critical operations

2. **Use HTTP tools for**:
   - Calling external APIs
   - Webhooks
   - Third-party integrations

3. **Use MCP servers for**:
   - Complex integrations (Gmail, Calendar, etc.)
   - When existing MCP server available

4. **Combine tools strategically**:
   - Read data with built-in tools
   - Process with Python tools
   - Communicate results with HTTP tools

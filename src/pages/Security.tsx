import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { Shield, AlertTriangle, CheckCircle, Eye, Lock, FileText, DollarSign,Key, RotateCcw, TrendingUp, } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Progress } from "@/components/ui/progress";
import { SecurityFinding } from "@/lib/mockData";
import { useToast } from "@/hooks/use-toast";

import { LineChart, Line, XAxis, YAxis, ResponsiveContainer } from "recharts";
const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.08
    }
  }
};

const itemVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: { opacity: 1, y: 0 }
};

const getSeverityColor = (severity: SecurityFinding['severity']) => {
  switch (severity) {
    case 'Critical': return 'status-critical';
    case 'High': return 'status-warning';
    case 'Medium': return 'bg-warning/10 text-warning border border-warning/20';
    case 'Low': return 'bg-muted text-muted-foreground';
    default: return 'bg-muted text-muted-foreground';
  }
};

const getSeverityIcon = (severity: SecurityFinding['severity']) => {
  switch (severity) {
    case 'Critical':
    case 'High':
      return <AlertTriangle className="h-4 w-4" />;
    case 'Medium':
      return <Eye className="h-4 w-4" />;
    case 'Low':
      return <FileText className="h-4 w-4" />;
    default:
      return <Shield className="h-4 w-4" />;
  }
};

const getKeyStatusColor = (status: string) => {
    switch (status) {
      case 'Expired': return 'status-critical';
      case 'Unused': return 'status-warning';
      default: return 'status-success';
    }
  };

export function Security() {
 

  const [findings, setFindings] = useState<SecurityFinding[]>([]);
  const [loading, setLoading] = useState(true);
  const { toast } = useToast();
  const [securityScore, setSecurityScore] = useState(0);
  const [scoreTrend, setScoreTrend] = useState<any[]>([]);
  const [weeklyData, setWeeklyData] = useState<any[]>([]);
  const [keys, setKeys] = useState<any[]>([]);


  useEffect(() => {
    fetchSecurityData();
    fetchSecurityData2();
  }, []);

  const fetchSecurityData = async () => {
    try {
      console.log("🔄 Attempting to fetch security data from backend...");
      const response = await fetch("http://localhost:8000/security", {
        method: "GET",
        headers: {
          "Content-Type": "application/json",
        },
      });
      
      if (!response.ok) {
        throw new Error(`Backend returned ${response.status}`);
      }
      
      const data = await response.json();
      console.log("📥 Backend response received:", data);
      console.log("✅ Successfully fetched security findings from backend:", data.findings?.length, "findings");
      setFindings(data.findings);
    } catch (error) {
      console.error("❌ Failed to fetch from backend:", error);
      console.log("📦 Using mock data as fallback");

      toast({
        title: "Backend Unavailable",
        description: "Restart server to fetch live alerts",
        variant: "destructive"
      });
    } finally {
      setLoading(false);
    }
  };
  const fetchSecurityData2 = async () => {
    try {
      console.log("🔄 Fetching security data from backend...");
      const response = await fetch("http://localhost:8000/security/data");
      
      if (!response.ok) {
        throw new Error(`Backend returned ${response.status}`);
      }
      
      const data = await response.json();
      console.log("✅ Successfully fetched security data:", data);
      setSecurityScore(data.score.current);
      setScoreTrend(data.score.trend);
      setWeeklyData(data.score.weeklyData || []);
      setKeys(data.keys);
    } catch (error) {
      console.error("❌ Failed to fetch security data:", error);
      setSecurityScore(0);
      setScoreTrend([]);
      setWeeklyData([]);
      setKeys([]);
    } finally {
      setLoading(false);
    }
  };
  const handleFixFinding = async (findingId: string) => {
    try {
      const response = await fetch("http://localhost:8000/security/update", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          finding_id: findingId,
          updates: { status: "Fixed" }
        })
      });

      if (response.ok) {
        setFindings(prev => prev.map(finding => 
          finding.id === findingId 
            ? { ...finding, status: "Fixed" as const }
            : finding
        ));
        
        const finding = findings.find(f => f.id === findingId);
        toast({
          title: "Security Issue Fixed",
          description: `${finding?.title} has been resolved successfully.`,
        });
      }
    } catch (error) {
      console.error("Failed to update finding:", error);
      toast({
        title: "Error",
        description: "Failed to apply fix",
        variant: "destructive"
      });
    }
  };

  const computeComplianceCoverage = (framework: string) => {
    const relatedFindings = findings.filter(f => f.compliance.includes(framework));

    if (relatedFindings.length === 0) {
      return 100; // No issues → fully compliant
    }

    const fixedCount = relatedFindings.filter(f => f.status === "Fixed").length;

    return Math.round((fixedCount / relatedFindings.length) * 100);
  };
  const handleRotateKey = (keyId: string) => {
    setKeys(prev => prev.map(key =>
      key.id === keyId
        ? { ...key, status: "Active" as const, lastUsed: new Date().toISOString() }
        : key
    ));

    // Improve security score
    const newScore = Math.min(100, securityScore + 5);
    setSecurityScore(newScore);

    toast({
      title: "🔄 Key Rotated Successfully",
      description: "Security key has been rotated and security score improved by +5 points.",
    });
  };

  const unusedKeys = keys.filter(k => k.status === 'Unused').length;
  const expiredKeys = keys.filter(k => k.status === 'Expired').length;

  
  
  const openFindings = findings.filter(f => f.status === 'Open').length;
  const fixedFindings = findings.filter(f => f.status === 'Fixed').length;
  const inProgressFindings = findings.filter(f => f.status === 'In Progress').length;
  const criticalFindings = findings.filter(f => f.severity === 'Critical' && f.status === 'Open').length;

  const securityScore1 = Math.round(((fixedFindings) / findings.length) * 100);
  const complianceItems = ['SOC 2', 'ISO 27001', 'CIS Benchmark'];
  

  return (
    <motion.div
      variants={containerVariants}
      initial="hidden"
      animate="visible"
      className="space-y-6"
    >
      {/* Header */}
      <motion.div variants={itemVariants}>
        <h1 className="text-3xl font-bold text-foreground">Security Dashboard</h1>
        <p className="text-muted-foreground mt-2">
          Monitor security posture and resolve vulnerabilities with AI recommendations
        </p>
      </motion.div>

      {/* Security Score & Metrics */}
      <motion.div variants={itemVariants} className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card className="metric-card">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div className="space-y-1">
                <p className="text-sm text-muted-foreground">Security Score</p>
                <p className="text-2xl font-bold text-success">{securityScore1}%</p>
              </div>
              <Shield className="h-8 w-8 text-success" />
            </div>
            <Progress value={securityScore1} className="mt-3 h-2" />
          </CardContent>
        </Card>

        <Card className="metric-card">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div className="space-y-1">
                <p className="text-sm text-muted-foreground">Critical Issues</p>
                <p className="text-2xl font-bold text-critical">{criticalFindings}</p>
              </div>
              <AlertTriangle className="h-8 w-8 text-critical" />
            </div>
          </CardContent>
        </Card>

        <Card className="metric-card">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div className="space-y-1">
                <p className="text-sm text-muted-foreground">Open Findings</p>
                <p className="text-2xl font-bold text-warning">{openFindings}</p>
              </div>
              <Eye className="h-8 w-8 text-warning" />
            </div>
          </CardContent>
        </Card>

        <Card className="metric-card">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div className="space-y-1">
                <p className="text-sm text-muted-foreground">Fixed</p>
                <p className="text-2xl font-bold text-success">{fixedFindings}</p>
              </div>
              <CheckCircle className="h-8 w-8 text-success" />
            </div>
          </CardContent>
        </Card>
      </motion.div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Security Findings */}
        <motion.div variants={itemVariants} className="lg:col-span-2">
          <Card className="dashboard-card">
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <AlertTriangle className="h-5 w-5" />
                <span>Security Findings</span>
              </CardTitle>
              <CardDescription>
                AI-detected security vulnerabilities and recommended fixes
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Accordion type="single" collapsible className="w-full">
                {findings.map((finding) => (
                  <AccordionItem key={finding.id} value={finding.id}>
                    <AccordionTrigger className="hover:no-underline">
                      <div className="flex items-center justify-between w-full pr-4">
                        <div className="flex items-center space-x-3">
                          {getSeverityIcon(finding.severity)}
                          <div className="text-left">
                            <p className="font-medium text-foreground">{finding.title}</p>
                            <p className="text-sm text-muted-foreground">{finding.resource}</p>
                          </div>
                        </div>
                        <div className="flex items-center space-x-2">
                          <Badge className={getSeverityColor(finding.severity)}>
                            {finding.severity}
                          </Badge>
                          {finding.status === 'Fixed' && (
                            <CheckCircle className="h-4 w-4 text-success" />
                          )}
                        </div>
                      </div>
                    </AccordionTrigger>
                    <AccordionContent className="pt-4">
                      <div className="space-y-4">
                        {/* Description */}
                        <div>
                          <h4 className="font-medium text-foreground mb-2">Description</h4>
                          <p className="text-sm text-muted-foreground">{finding.description}</p>
                        </div>

                        {/* Compliance Impact */}
                        <div>
                          <h4 className="font-medium text-foreground mb-2">Compliance Impact</h4>
                          <div className="flex flex-wrap gap-2">
                            {finding.compliance.map((comp) => (
                              <Badge key={comp} variant="outline" className="text-xs">
                                {comp}
                              </Badge>
                            ))}
                          </div>
                        </div>

                        {/* Remediation */}
                        <div>
                          <h4 className="font-medium text-foreground mb-2">AI Remediation</h4>

                          {/* Title */}
                          <div className="p-3 bg-primary/5 border border-primary/20 rounded-lg space-y-3">
                            <p className="text-sm font-semibold">{finding.remediation.title}</p>

                            {/* Steps */}
                            <div className="space-y-3">
                              {finding.remediation.steps?.map((step) => (
                                <div
                                  key={step.step}
                                  className="p-3 rounded-md bg-muted border border-muted-foreground/20"
                                >
                                  <p className="text-sm font-medium mb-1">Step {step.step}</p>
                                  <p className="text-xs text-muted-foreground mb-2">{step.description}</p>

                                  {/* Command block */}
                                  <pre className="text-xs bg-background p-2 rounded-md border overflow-auto">
                                    {step.command}
                                  </pre>
                                </div>
                              ))}
                            </div>
                          </div>
                        </div>

                        {/* Cost Impact */}
                        {finding.estimatedCost !== undefined && finding.estimatedCost !== null && (
                        <div>
                          <h4 className="font-medium text-foreground mb-2">Cost Impact</h4>
                          <div className="flex items-center space-x-2">
                            <DollarSign className="h-4 w-4 text-success" />
                            <span className="text-sm text-success font-medium">
                              Additional ${finding.estimatedCost}/month for security controls
                            </span>
                          </div>
                        </div>
                      )}


                        {/* Actions */}
                        <div className="flex space-x-3 pt-2">
                          {finding.status !== 'Fixed' ? (
                            <>
                              <Button
                                size="sm"
                                onClick={() => handleFixFinding(finding.id)}
                                className="action-success"
                              >
                                Apply Fix
                              </Button>
                             
                            </>
                          ) : (
                            <div className="flex items-center space-x-2 text-success">
                              <CheckCircle className="h-4 w-4" />
                              <span className="text-sm font-medium">Issue Resolved</span>
                            </div>
                          )}
                        </div>
                      </div>
                    </AccordionContent>
                  </AccordionItem>
                ))}
              </Accordion>
            </CardContent>
          </Card>
        </motion.div>

        {/* Compliance & Insights */}
        <motion.div variants={itemVariants} className="space-y-6">
          {/* Compliance Status */}
          <Card className="dashboard-card">
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <FileText className="h-5 w-5" />
                <span>Compliance Status</span>
              </CardTitle>
              <CardDescription>
                Current compliance framework coverage
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {complianceItems.map((item) => {
                const coverage = computeComplianceCoverage(item);

                return (
                  <div key={item} className="space-y-2">
                    <div className="flex justify-between text-sm">
                      <span className="font-medium">{item}</span>
                      <span className="text-muted-foreground">{coverage}%</span>
                    </div>
                    <Progress value={coverage} className="h-2" />
                  </div>
                );
              })}
            </CardContent>
          </Card>

          {/* Security Trends */}
          <Card className="dashboard-card">
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <Shield className="h-5 w-5" />
                <span>Security Insights</span>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-3">
                <div className="p-3 bg-success/5 border border-success/20 rounded-lg">
                  <div className="flex items-center space-x-2 mb-1">
                    <CheckCircle className="h-4 w-4 text-success" />
                    <span className="text-sm font-medium text-success">Improvement</span>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Security score improved by 15% this month
                  </p>
                </div>

                <div className="p-3 bg-warning/5 border border-warning/20 rounded-lg">
                  <div className="flex items-center space-x-2 mb-1">
                    <AlertTriangle className="h-4 w-4 text-warning" />
                    <span className="text-sm font-medium text-warning">Action Required</span>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {criticalFindings} critical issues need immediate attention
                  </p>
                </div>

                <div className="p-3 bg-primary/5 border border-primary/20 rounded-lg">
                  <div className="flex items-center space-x-2 mb-1">
                    <Lock className="h-4 w-4 text-primary" />
                    <span className="text-sm font-medium text-primary">Dual Benefit</span>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Security fixes can save $15/month in compliance costs
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>

         
        </motion.div>
      </div>

      {/* Advanced AI Features */}
      {/* <ComplianceWatchdog /> */}
        <motion.div variants={itemVariants}>
          <Card className="dashboard-card">
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <Shield className="h-5 w-5 text-success" />
                <span>Cloud Security Health Score</span>
              </CardTitle>
              <CardDescription>
                Overall security posture with weekly trending
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <div className="space-y-4">
                  <div className="text-center">
                    <div className="relative inline-block">
                      <svg className="w-32 h-32 transform -rotate-90" viewBox="0 0 100 100">
                        <circle
                          cx="50"
                          cy="50"
                          r="40"
                          stroke="hsl(var(--muted))"
                          strokeWidth="8"
                          fill="none"
                        />
                        <motion.circle
                          cx="50"
                          cy="50"
                          r="40"
                          stroke="hsl(var(--success))"
                          strokeWidth="8"
                          fill="none"
                          strokeDasharray={`${2 * Math.PI * 40}`}
                          strokeDashoffset={`${2 * Math.PI * 40 * (1 - securityScore / 100)}`}
                          initial={{ strokeDashoffset: 2 * Math.PI * 40 }}
                          animate={{ strokeDashoffset: 2 * Math.PI * 40 * (1 - securityScore / 100) }}
                          transition={{ duration: 1, ease: "easeOut" }}
                          strokeLinecap="round"
                        />
                      </svg>
                      <div className="absolute inset-0 flex items-center justify-center">
                        <div className="text-center">
                          <div className="text-3xl font-bold text-success">{securityScore}</div>
                          <div className="text-xs text-muted-foreground">Score</div>
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-4 text-center">
                    <div className="p-3 bg-success/5 border border-success/20 rounded-lg">
                      <TrendingUp className="h-5 w-5 text-success mx-auto mb-1" />
                      <p className="text-sm font-medium text-success">+3</p>
                      <p className="text-xs text-muted-foreground">This week</p>
                    </div>
                    <div className="p-3 bg-muted/30 rounded-lg">
                      <Shield className="h-5 w-5 text-foreground mx-auto mb-1" />
                      <p className="text-sm font-medium">Industry Avg</p>
                      <p className="text-xs text-muted-foreground">73</p>
                    </div>
                  </div>
                </div>

                <div>
                  <h4 className="font-medium mb-3">Weekly Security Trend</h4>
                  <div className="h-32">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={weeklyData}>
                        <XAxis dataKey="day" axisLine={false} tickLine={false} />
                        <YAxis hide />
                        <Line
                          type="monotone"
                          dataKey="score"
                          stroke="hsl(var(--success))"
                          strokeWidth={3}
                          dot={{ fill: 'hsl(var(--success))', strokeWidth: 2, r: 4 }}
                          activeDot={{ r: 6 }}
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </motion.div>

      {/* Unused Keys & Service Accounts */}
      <motion.div variants={itemVariants}>
        <Card className="dashboard-card">
          <CardHeader>
            <CardTitle className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <Key className="h-5 w-5 text-warning" />
                <span>Security Keys & Accounts</span>
              </div>
              <div className="flex items-center space-x-2">
                {unusedKeys > 0 && (
                  <Badge className="status-warning">
                    {unusedKeys} unused
                  </Badge>
                )}
                {expiredKeys > 0 && (
                  <Badge className="status-critical">
                    {expiredKeys} expired
                  </Badge>
                )}
              </div>
            </CardTitle>
            <CardDescription>
              Manage unused keys and service accounts to improve security posture
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {keys.map((key) => (
                <div
                  key={key.id}
                  className="flex items-center justify-between p-4 border rounded-lg hover:bg-muted/30 transition-colors"
                >
                  <div className="flex items-center space-x-4">
                    <div className="flex items-center justify-center w-10 h-10 bg-muted/50 rounded-lg">
                      <Key className="h-5 w-5 text-muted-foreground" />
                    </div>
                    
                    <div>
                      <div className="flex items-center space-x-2 mb-1">
                        <p className="font-medium text-foreground">{key.name}</p>
                        <Badge variant="outline" className="text-xs">{key.type}</Badge>
                        <Badge className={getKeyStatusColor(key.status)}>
                          {key.status}
                        </Badge>
                      </div>
                      <div className="flex items-center space-x-4 text-xs text-muted-foreground">
                        <span>Last used: {key.lastUsed === "Never" 
                          ? "Never" 
                          : new Date(key.lastUsed).toLocaleDateString()
                        }</span>
                        <span>
                          {key.expiresIn > 0 ? `Expires in ${key.expiresIn} days` : `Expired ${Math.abs(key.expiresIn)} days ago`}
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center space-x-2">
                    {key.status !== 'Active' && (
                      <Button
                        size="sm"
                        onClick={() => handleRotateKey(key.id)}
                        className="action-primary"
                      >
                        <RotateCcw className="h-4 w-4 mr-2" />
                        Rotate Key
                      </Button>
                    )}
                  </div>
                </div>
              ))}
            </div>

            {keys.filter(k => k.status !== 'Active').length === 0 && (
              <div className="text-center py-8">
                <Shield className="h-12 w-12 text-success mx-auto mb-4" />
                <p className="text-lg font-medium text-success">All keys are secure!</p>
                <p className="text-sm text-muted-foreground">No unused or expired keys detected</p>
              </div>
            )}
          </CardContent>
        </Card>
      </motion.div>
    </motion.div>
  );
}
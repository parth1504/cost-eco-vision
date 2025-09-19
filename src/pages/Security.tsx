import { useState } from "react";
import { motion } from "framer-motion";
import { Shield, AlertTriangle, CheckCircle, Eye, Lock, FileText, DollarSign } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Progress } from "@/components/ui/progress";
import { mockSecurityFindings, SecurityFinding } from "@/lib/mockData";
import { useToast } from "@/hooks/use-toast";
import { ComplianceWatchdog } from "@/components/advanced/ComplianceWatchdog";

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

export function Security() {
  const [findings, setFindings] = useState<SecurityFinding[]>(mockSecurityFindings);
  const { toast } = useToast();

  const handleFixFinding = (findingId: string) => {
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
  };

  const openFindings = findings.filter(f => f.status === 'Open').length;
  const fixedFindings = findings.filter(f => f.status === 'Fixed').length;
  const inProgressFindings = findings.filter(f => f.status === 'In Progress').length;
  const criticalFindings = findings.filter(f => f.severity === 'Critical' && f.status === 'Open').length;

  const securityScore = Math.round(((fixedFindings) / findings.length) * 100);
  const complianceItems = ['SOC 2', 'ISO 27001', 'GDPR', 'HIPAA', 'CIS Benchmark'];

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
                <p className="text-2xl font-bold text-success">{securityScore}%</p>
              </div>
              <Shield className="h-8 w-8 text-success" />
            </div>
            <Progress value={securityScore} className="mt-3 h-2" />
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
                          <div className="p-3 bg-primary/5 border border-primary/20 rounded-lg">
                            <p className="text-sm text-foreground">{finding.remediation}</p>
                          </div>
                        </div>

                        {/* Cost Impact */}
                        {finding.estimatedCost && (
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
                              <Button size="sm" variant="outline">
                                Mark In Progress
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
                const coverage = Math.floor(Math.random() * 30) + 70; // Mock coverage percentage
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
                    Security fixes can save $156/month in compliance costs
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Quick Actions */}
          <Card className="dashboard-card">
            <CardHeader>
              <CardTitle className="text-base">Quick Actions</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <Button className="w-full action-primary">
                <Shield className="h-4 w-4 mr-2" />
                Run Security Scan
              </Button>
              <Button variant="outline" className="w-full">
                <FileText className="h-4 w-4 mr-2" />
                Generate Report
              </Button>
              <Button variant="outline" className="w-full">
                <Lock className="h-4 w-4 mr-2" />
                Review Policies
              </Button>
            </CardContent>
          </Card>
        </motion.div>
      </div>

      {/* Advanced AI Features */}
      <ComplianceWatchdog />
    </motion.div>
  );
}
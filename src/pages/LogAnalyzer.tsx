import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { FileSearch, AlertTriangle, CheckCircle, Clock, ArrowRight, RefreshCw, Terminal } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const containerVariants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { staggerChildren: 0.1 } }
};
const itemVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: { opacity: 1, y: 0 }
};

export function LogAnalyser() {
  const [logGroups, setLogGroups] = useState<any[]>([]);
  const [selectedGroup, setSelectedGroup] = useState<string>("");
  const [analysis, setAnalysis] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchLogGroups();
  }, []);

  const fetchLogGroups = async () => {
    try {
      const res = await fetch("http://localhost:8000/logs/groups");
      if (res.ok) setLogGroups(await res.json());
    } catch (e) {
      console.error("Failed to fetch log groups:", e);
    }
  };

  const runAnalysis = async () => {
    if (!selectedGroup) return;
    setLoading(true);
    setAnalysis(null);
    try {
      const res = await fetch("http://localhost:8000/logs/analyse", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ log_group: selectedGroup }),
      });
      if (res.ok) setAnalysis(await res.json());
    } catch (e) {
      console.error("Analysis failed:", e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <motion.div variants={containerVariants} initial="hidden" animate="visible" className="space-y-6">
      <motion.div variants={itemVariants}>
        <h1 className="text-3xl font-bold text-foreground">Log Analyser</h1>
        <p className="text-muted-foreground mt-2">
          CloudWatch log diff analysis — compare error state against last healthy baseline
        </p>
      </motion.div>

      {/* Controls */}
      <motion.div variants={itemVariants}>
        <Card className="dashboard-card">
          <CardContent className="pt-6">
            <div className="flex items-center gap-4">
              <div className="flex-1">
                <Select value={selectedGroup} onValueChange={setSelectedGroup}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select a CloudWatch log group..." />
                  </SelectTrigger>
                  <SelectContent>
                    {logGroups.map((g) => (
                      <SelectItem key={g.name} value={g.name}>{g.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <Button onClick={runAnalysis} disabled={!selectedGroup || loading}>
                {loading ? <RefreshCw className="h-4 w-4 mr-2 animate-spin" /> : <FileSearch className="h-4 w-4 mr-2" />}
                {loading ? "Analysing..." : "Analyse Logs"}
              </Button>
            </div>
          </CardContent>
        </Card>
      </motion.div>

      {/* Analysis Results */}
      {analysis?.status === "complete" && (
        <>
          {/* LLM Analysis Summary */}
          {analysis.analysis && (
            <motion.div variants={itemVariants}>
              <Card className="dashboard-card border-warning/30">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-base">
                    <AlertTriangle className="h-5 w-5 text-warning" />
                    Analysis Summary
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div>
                    <p className="text-sm font-medium text-foreground">{analysis.analysis.summary}</p>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                    <div className="p-3 bg-destructive/5 border border-destructive/20 rounded-lg">
                      <p className="text-xs text-muted-foreground mb-1">Root Cause</p>
                      <p className="text-sm">{analysis.analysis.root_cause}</p>
                    </div>
                    <div className="p-3 bg-warning/5 border border-warning/20 rounded-lg">
                      <p className="text-xs text-muted-foreground mb-1">Evidence</p>
                      <p className="text-sm">{analysis.analysis.evidence}</p>
                    </div>
                    <div className="p-3 bg-success/5 border border-success/20 rounded-lg">
                      <p className="text-xs text-muted-foreground mb-1">Recommendation</p>
                      <p className="text-sm">{analysis.analysis.recommendation}</p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </motion.div>
          )}

          {/* Diff Stats */}
          <motion.div variants={itemVariants}>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <Card className="dashboard-card">
                <CardContent className="pt-4 text-center">
                  <p className="text-2xl font-bold text-destructive">{analysis.diff.error_count_after}</p>
                  <p className="text-xs text-muted-foreground">Errors (now)</p>
                </CardContent>
              </Card>
              <Card className="dashboard-card">
                <CardContent className="pt-4 text-center">
                  <p className="text-2xl font-bold text-success">{analysis.diff.error_count_before}</p>
                  <p className="text-xs text-muted-foreground">Errors (before)</p>
                </CardContent>
              </Card>
              <Card className="dashboard-card">
                <CardContent className="pt-4 text-center">
                  <p className="text-2xl font-bold text-warning">+{analysis.diff.count_increase}</p>
                  <p className="text-xs text-muted-foreground">Increase</p>
                </CardContent>
              </Card>
              <Card className="dashboard-card">
                <CardContent className="pt-4 text-center">
                  <p className="text-2xl font-bold text-primary">{analysis.diff.new_pattern_count}</p>
                  <p className="text-xs text-muted-foreground">New patterns</p>
                </CardContent>
              </Card>
            </div>
          </motion.div>

          {/* Side-by-side Log Diff */}
          <motion.div variants={itemVariants}>
            <Card className="dashboard-card">
              <CardHeader>
                <CardTitle className="text-base flex items-center gap-2">
                  <Terminal className="h-5 w-5" />
                  Log Diff — Side by Side
                </CardTitle>
                <CardDescription>Healthy baseline (left) vs Current errors (right)</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                  {/* Healthy */}
                  <div>
                    <div className="flex items-center gap-2 mb-2">
                      <CheckCircle className="h-4 w-4 text-success" />
                      <span className="text-sm font-medium text-success">Healthy Window</span>
                      <Badge variant="secondary" className="text-[10px]">
                        {analysis.time_range.healthy_window.start.slice(11, 19)} — {analysis.time_range.healthy_window.end.slice(11, 19)}
                      </Badge>
                    </div>
                    <div className="bg-muted/30 rounded-lg p-3 max-h-80 overflow-y-auto font-mono text-xs space-y-1">
                      {analysis.healthy_logs.length > 0 ? (
                        analysis.healthy_logs.map((log: any, i: number) => (
                          <div key={i} className="flex gap-2">
                            <span className="text-muted-foreground whitespace-nowrap">{log.timestamp?.slice(11, 19)}</span>
                            <span className="text-foreground/80 break-all">{log.message}</span>
                          </div>
                        ))
                      ) : (
                        <p className="text-muted-foreground italic">No errors in healthy window</p>
                      )}
                    </div>
                  </div>

                  {/* Error */}
                  <div>
                    <div className="flex items-center gap-2 mb-2">
                      <AlertTriangle className="h-4 w-4 text-destructive" />
                      <span className="text-sm font-medium text-destructive">Error Window</span>
                      <Badge variant="destructive" className="text-[10px]">
                        {analysis.time_range.error_window.start.slice(11, 19)} — {analysis.time_range.error_window.end.slice(11, 19)}
                      </Badge>
                    </div>
                    <div className="bg-destructive/5 rounded-lg p-3 max-h-80 overflow-y-auto font-mono text-xs space-y-1">
                      {analysis.error_logs.length > 0 ? (
                        analysis.error_logs.map((log: any, i: number) => (
                          <div key={i} className="flex gap-2">
                            <span className="text-muted-foreground whitespace-nowrap">{log.timestamp?.slice(11, 19)}</span>
                            <span className="text-destructive/90 break-all">{log.message}</span>
                          </div>
                        ))
                      ) : (
                        <p className="text-muted-foreground italic">No errors detected</p>
                      )}
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          </motion.div>

          {/* New Error Patterns */}
          {analysis.diff.new_error_patterns?.length > 0 && (
            <motion.div variants={itemVariants}>
              <Card className="dashboard-card border-destructive/20">
                <CardHeader>
                  <CardTitle className="text-base">New Error Patterns</CardTitle>
                  <CardDescription>Patterns appearing in error window that were absent during healthy operation</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    {analysis.diff.new_error_patterns.slice(0, 10).map((pattern: string, i: number) => (
                      <div key={i} className="flex items-start gap-2 p-2 bg-destructive/5 rounded text-xs font-mono">
                        <ArrowRight className="h-3 w-3 mt-0.5 text-destructive flex-shrink-0" />
                        <span className="break-all">{pattern}</span>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            </motion.div>
          )}

          {/* Infra Changes */}
          {analysis.infra_changes?.length > 0 && (
            <motion.div variants={itemVariants}>
              <Card className="dashboard-card">
                <CardHeader>
                  <CardTitle className="text-base flex items-center gap-2">
                    <Clock className="h-4 w-4" />
                    Infrastructure Changes in Timeframe
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    {analysis.infra_changes.map((change: any, i: number) => (
                      <div key={i} className="flex items-center justify-between p-2 bg-muted/30 rounded text-sm">
                        <div className="flex items-center gap-2">
                          <Badge variant="secondary">{change.event}</Badge>
                          <span className="text-muted-foreground">by {change.user}</span>
                        </div>
                        <span className="text-xs text-muted-foreground">{change.time}</span>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            </motion.div>
          )}
        </>
      )}

      {/* Error state */}
      {analysis?.status === "error" && (
        <motion.div variants={itemVariants}>
          <Card className="dashboard-card border-destructive/30">
            <CardContent className="pt-6 text-center">
              <AlertTriangle className="h-8 w-8 text-destructive mx-auto mb-2" />
              <p className="text-sm text-destructive">{analysis.error}</p>
            </CardContent>
          </Card>
        </motion.div>
      )}
    </motion.div>
  );
}

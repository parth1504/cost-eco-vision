import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  FileSearch, AlertTriangle, CheckCircle, Clock, ArrowRight, RefreshCw,
  Terminal, GitPullRequest, Zap, Shield, Code, Eye, ChevronDown, ChevronRight,
  Database, Globe, Server, Activity, Brain, Search, Layers, Target
} from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Progress } from "@/components/ui/progress";

const containerVariants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { staggerChildren: 0.08 } }
};
const itemVariants = {
  hidden: { opacity: 0, y: 16 },
  visible: { opacity: 1, y: 0 }
};

function RiskBadge({ level }: { level: string }) {
  const variant = level === "high" ? "destructive" : level === "medium" ? "secondary" : "default";
  const icon = level === "high" ? <AlertTriangle className="h-3 w-3" /> : level === "medium" ? <Shield className="h-3 w-3" /> : <CheckCircle className="h-3 w-3" />;
  return <Badge variant={variant} className="gap-1">{icon}{level}</Badge>;
}

function ExpandableSection({ title, icon: Icon, children, defaultOpen = false }: any) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border border-border rounded-lg overflow-hidden">
      <button onClick={() => setOpen(!open)} className="w-full flex items-center gap-2 p-3 hover:bg-muted/30 transition-colors text-left">
        {Icon && <Icon className="h-4 w-4 text-muted-foreground" />}
        <span className="text-sm font-medium flex-1">{title}</span>
        {open ? <ChevronDown className="h-4 w-4 text-muted-foreground" /> : <ChevronRight className="h-4 w-4 text-muted-foreground" />}
      </button>
      <AnimatePresence>
        {open && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.2 }}>
            <div className="p-3 pt-0 border-t border-border">{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ─── PR Intelligence Tab ───────────────────────────────────────────────────

function PRIntelligence() {
  const [prNumber, setPrNumber] = useState("");
  const [analysis, setAnalysis] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [indexStatus, setIndexStatus] = useState<any>(null);

  useEffect(() => { fetchIndexStats(); }, []);

  const fetchIndexStats = async () => {
    try {
      const res = await fetch("http://localhost:8000/intelligence/index/stats");
      if (res.ok) setIndexStatus(await res.json());
    } catch {}
  };

  const reindex = async () => {
    try {
      const res = await fetch("http://localhost:8000/intelligence/index", { method: "POST" });
      if (res.ok) { setIndexStatus(await res.json()); }
    } catch {}
  };

  const analyzePR = async () => {
    if (!prNumber) return;
    setLoading(true);
    setAnalysis(null);
    try {
      const res = await fetch("http://localhost:8000/intelligence/pr/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pr_number: parseInt(prNumber) }),
      });
      if (res.ok) setAnalysis(await res.json());
    } catch (e) {
      console.error("PR analysis failed:", e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-5">
      {/* Controls */}
      <Card className="dashboard-card">
        <CardContent className="pt-5">
          <div className="flex items-center gap-3">
            <div className="flex-1">
              <input
                type="number"
                placeholder="Enter PR number..."
                value={prNumber}
                onChange={(e) => setPrNumber(e.target.value)}
                className="w-full px-3 py-2 bg-background border border-input rounded-md text-sm"
              />
            </div>
            <Button onClick={analyzePR} disabled={!prNumber || loading}>
              {loading ? <RefreshCw className="h-4 w-4 mr-2 animate-spin" /> : <Brain className="h-4 w-4 mr-2" />}
              {loading ? "Analyzing..." : "Analyze PR"}
            </Button>
            <Button variant="outline" size="sm" onClick={reindex}>
              <Layers className="h-4 w-4 mr-1" />
              Re-index
            </Button>
          </div>
          {indexStatus && (
            <div className="flex gap-4 mt-3 text-xs text-muted-foreground">
              <span>Indexed: {indexStatus.indexed_files} files</span>
              <span>Chunks: {indexStatus.total_chunks}</span>
              <span>Dependencies: {indexStatus.dependency_edges} edges</span>
              <span>{indexStatus.chroma_available ? "ChromaDB active" : "Fallback mode"}</span>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Analysis Results */}
      {analysis?.status === "complete" && (
        <motion.div variants={containerVariants} initial="hidden" animate="visible" className="space-y-4">
          {/* Step 1: What Changed */}
          <motion.div variants={itemVariants}>
            <Card className="dashboard-card">
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base flex items-center gap-2">
                    <div className="p-1.5 bg-primary/10 rounded"><GitPullRequest className="h-4 w-4 text-primary" /></div>
                    What Changed
                  </CardTitle>
                  <div className="flex items-center gap-2">
                    <Badge variant="secondary">{analysis.pr.files_changed} files</Badge>
                    <span className="text-xs text-success">+{analysis.pr.additions}</span>
                    <span className="text-xs text-destructive">-{analysis.pr.deletions}</span>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="flex flex-wrap gap-2">
                  {analysis.change_summary.services_touched?.map((s: string) => (
                    <Badge key={s} variant="outline" className="gap-1"><Server className="h-3 w-3" />{s}</Badge>
                  ))}
                </div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                  {Object.entries(analysis.change_summary.categories || {}).map(([cat, files]: any) => (
                    <div key={cat} className="p-2 bg-muted/30 rounded text-center">
                      <p className="text-lg font-bold">{files.length}</p>
                      <p className="text-[10px] text-muted-foreground">{cat.replace("_", " ")}</p>
                    </div>
                  ))}
                </div>
                {analysis.change_summary.functions_modified?.length > 0 && (
                  <ExpandableSection title={`${analysis.change_summary.functions_modified.length} functions modified`} icon={Code}>
                    <div className="space-y-1 mt-2">
                      {analysis.change_summary.functions_modified.map((f: any, i: number) => (
                        <div key={i} className="flex items-center gap-2 text-xs font-mono">
                          <span className="text-primary">{f.function}()</span>
                          <span className="text-muted-foreground">in {f.file}</span>
                        </div>
                      ))}
                    </div>
                  </ExpandableSection>
                )}
              </CardContent>
            </Card>
          </motion.div>

          {/* Step 2: Impact Analysis */}
          <motion.div variants={itemVariants}>
            <Card className="dashboard-card">
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base flex items-center gap-2">
                    <div className="p-1.5 bg-warning/10 rounded"><Target className="h-4 w-4 text-warning" /></div>
                    System Impact
                  </CardTitle>
                  <RiskBadge level={analysis.impact_analysis.blast_radius} />
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="grid grid-cols-3 gap-3">
                  <div className="p-3 bg-muted/30 rounded-lg text-center">
                    <p className="text-2xl font-bold">{analysis.impact_analysis.affected_files_count}</p>
                    <p className="text-xs text-muted-foreground">Affected files</p>
                  </div>
                  <div className="p-3 bg-muted/30 rounded-lg text-center">
                    <p className="text-2xl font-bold">{analysis.impact_analysis.dependency_chains?.length || 0}</p>
                    <p className="text-xs text-muted-foreground">Dep chains</p>
                  </div>
                  <div className="p-3 bg-muted/30 rounded-lg text-center">
                    <p className="text-2xl font-bold">{analysis.impact_analysis.related_code?.length || 0}</p>
                    <p className="text-xs text-muted-foreground">Related modules</p>
                  </div>
                </div>

                {analysis.impact_analysis.dependency_chains?.length > 0 && (
                  <ExpandableSection title="Dependency Cascade" icon={Layers}>
                    <div className="space-y-2 mt-2">
                      {analysis.impact_analysis.dependency_chains.slice(0, 5).map((chain: any, i: number) => (
                        <div key={i} className="text-xs">
                          <div className="flex items-center gap-1">
                            <span className="font-mono text-primary">{chain.changed_file}</span>
                            <ArrowRight className="h-3 w-3 text-muted-foreground" />
                            <span className="text-muted-foreground">{chain.cascade_depth} dependents</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </ExpandableSection>
                )}
              </CardContent>
            </Card>
          </motion.div>

          {/* Step 3: Infrastructure Risk */}
          <motion.div variants={itemVariants}>
            <Card className="dashboard-card">
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base flex items-center gap-2">
                    <div className="p-1.5 bg-destructive/10 rounded"><Activity className="h-4 w-4 text-destructive" /></div>
                    Infrastructure Risk
                  </CardTitle>
                  <RiskBadge level={analysis.infra_risk.overall_risk} />
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                {analysis.infra_risk.risk_signals?.length > 0 ? (
                  <div className="space-y-2">
                    {analysis.infra_risk.risk_signals.map((signal: any, i: number) => (
                      <div key={i} className="flex items-start gap-3 p-2 bg-muted/20 rounded">
                        <RiskBadge level={signal.risk} />
                        <div className="flex-1">
                          <p className="text-sm font-medium">{signal.signal}</p>
                          <p className="text-xs text-muted-foreground">{signal.detail}</p>
                        </div>
                        <Badge variant="outline" className="text-[10px]">{signal.category}</Badge>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-success">No infrastructure risks detected</p>
                )}

                {/* Production Readiness */}
                <ExpandableSection title={`Production Readiness: ${Math.round(analysis.infra_risk.production_readiness?.score || 0)}%`} icon={CheckCircle}>
                  <div className="space-y-2 mt-2">
                    <Progress value={analysis.infra_risk.production_readiness?.score || 0} className="h-2" />
                    {analysis.infra_risk.production_readiness?.checks?.map((check: any, i: number) => (
                      <div key={i} className="flex items-center gap-2 text-xs">
                        {check.passed ? <CheckCircle className="h-3.5 w-3.5 text-success" /> : <AlertTriangle className="h-3.5 w-3.5 text-destructive" />}
                        <span className={check.passed ? "" : "text-destructive"}>{check.check}</span>
                        <span className="text-muted-foreground ml-auto">{check.detail}</span>
                      </div>
                    ))}
                  </div>
                </ExpandableSection>
              </CardContent>
            </Card>
          </motion.div>

          {/* Step 4: AI Reasoning */}
          <motion.div variants={itemVariants}>
            <Card className="dashboard-card border-primary/20">
              <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center gap-2">
                  <div className="p-1.5 bg-primary/10 rounded"><Brain className="h-4 w-4 text-primary" /></div>
                  AI Analysis
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {analysis.reasoning?.summary && (
                  <div className="p-3 bg-primary/5 border border-primary/20 rounded-lg">
                    <p className="text-sm font-medium">{analysis.reasoning.summary}</p>
                  </div>
                )}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {analysis.reasoning?.risk_assessment && (
                    <div className="p-3 bg-muted/30 rounded-lg">
                      <p className="text-[10px] text-muted-foreground uppercase font-medium mb-1">Risk Assessment</p>
                      <p className="text-xs">{analysis.reasoning.risk_assessment}</p>
                    </div>
                  )}
                  {analysis.reasoning?.infra_impact && (
                    <div className="p-3 bg-muted/30 rounded-lg">
                      <p className="text-[10px] text-muted-foreground uppercase font-medium mb-1">Infra Impact</p>
                      <p className="text-xs">{analysis.reasoning.infra_impact}</p>
                    </div>
                  )}
                </div>
                {analysis.reasoning?.edge_cases?.length > 0 && (
                  <div className="p-3 bg-warning/5 border border-warning/20 rounded-lg">
                    <p className="text-[10px] text-muted-foreground uppercase font-medium mb-1">Edge Cases</p>
                    <div className="space-y-1">
                      {analysis.reasoning.edge_cases.map((ec: string, i: number) => (
                        <div key={i} className="flex items-start gap-1.5 text-xs">
                          <AlertTriangle className="h-3 w-3 mt-0.5 text-warning flex-shrink-0" />
                          <span>{ec}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {analysis.reasoning?.recommendation && (
                  <div className="p-3 bg-success/5 border border-success/20 rounded-lg">
                    <p className="text-[10px] text-muted-foreground uppercase font-medium mb-1">Recommendation</p>
                    <p className="text-xs font-medium">{analysis.reasoning.recommendation}</p>
                  </div>
                )}
              </CardContent>
            </Card>
          </motion.div>
        </motion.div>
      )}

      {analysis?.status === "error" && (
        <Card className="dashboard-card border-destructive/30">
          <CardContent className="pt-6 text-center">
            <AlertTriangle className="h-8 w-8 text-destructive mx-auto mb-2" />
            <p className="text-sm text-destructive">{analysis.error}</p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// ─── Log Intelligence Tab ──────────────────────────────────────────────────

function LogIntelligence() {
  const [logGroups, setLogGroups] = useState<any[]>([]);
  const [selectedGroup, setSelectedGroup] = useState("");
  const [analysis, setAnalysis] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => { fetchLogGroups(); }, []);

  const fetchLogGroups = async () => {
    try {
      const res = await fetch("http://localhost:8000/logs/groups");
      if (res.ok) setLogGroups(await res.json());
    } catch {}
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
    } catch {}
    finally { setLoading(false); }
  };

  return (
    <div className="space-y-5">
      {/* Controls */}
      <Card className="dashboard-card">
        <CardContent className="pt-5">
          <div className="flex items-center gap-3">
            <div className="flex-1">
              <Select value={selectedGroup} onValueChange={setSelectedGroup}>
                <SelectTrigger><SelectValue placeholder="Select a CloudWatch log group..." /></SelectTrigger>
                <SelectContent>
                  {logGroups.map((g) => (
                    <SelectItem key={g.name} value={g.name}>{g.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <Button onClick={runAnalysis} disabled={!selectedGroup || loading}>
              {loading ? <RefreshCw className="h-4 w-4 mr-2 animate-spin" /> : <Zap className="h-4 w-4 mr-2" />}
              {loading ? "Analyzing..." : "Analyze Logs"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {analysis?.status === "complete" && (
        <motion.div variants={containerVariants} initial="hidden" animate="visible" className="space-y-4">
          {/* Reasoning Flow */}
          <motion.div variants={itemVariants}>
            <div className="flex items-center gap-2 text-xs text-muted-foreground mb-2">
              <Badge variant="outline" className="gap-1"><Zap className="h-3 w-3" />Event Detected</Badge>
              <ArrowRight className="h-3 w-3" />
              <Badge variant="outline" className="gap-1"><Search className="h-3 w-3" />Logs Compared</Badge>
              <ArrowRight className="h-3 w-3" />
              <Badge variant="outline" className="gap-1"><Code className="h-3 w-3" />Code Correlated</Badge>
              <ArrowRight className="h-3 w-3" />
              <Badge variant="outline" className="gap-1"><Brain className="h-3 w-3" />Conclusion</Badge>
            </div>
          </motion.div>

          {/* AI Analysis */}
          {analysis.analysis && (
            <motion.div variants={itemVariants}>
              <Card className="dashboard-card border-warning/30">
                <CardHeader className="pb-3">
                  <CardTitle className="text-base flex items-center gap-2">
                    <div className="p-1.5 bg-warning/10 rounded"><Brain className="h-4 w-4 text-warning" /></div>
                    Root Cause Analysis
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="p-3 bg-warning/5 border border-warning/20 rounded-lg mb-3">
                    <p className="text-sm font-medium">{analysis.analysis.summary}</p>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                    <div className="p-3 bg-destructive/5 border border-destructive/20 rounded-lg">
                      <p className="text-[10px] text-muted-foreground uppercase font-medium mb-1">Root Cause</p>
                      <p className="text-xs">{analysis.analysis.root_cause}</p>
                    </div>
                    <div className="p-3 bg-muted/30 rounded-lg">
                      <p className="text-[10px] text-muted-foreground uppercase font-medium mb-1">Evidence</p>
                      <p className="text-xs">{analysis.analysis.evidence}</p>
                    </div>
                    <div className="p-3 bg-success/5 border border-success/20 rounded-lg">
                      <p className="text-[10px] text-muted-foreground uppercase font-medium mb-1">Fix</p>
                      <p className="text-xs">{analysis.analysis.recommendation}</p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </motion.div>
          )}

          {/* Diff Stats */}
          <motion.div variants={itemVariants}>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <Card className="dashboard-card"><CardContent className="pt-4 text-center">
                <p className="text-2xl font-bold text-destructive">{analysis.diff.error_count_after}</p>
                <p className="text-xs text-muted-foreground">Errors now</p>
              </CardContent></Card>
              <Card className="dashboard-card"><CardContent className="pt-4 text-center">
                <p className="text-2xl font-bold text-success">{analysis.diff.error_count_before}</p>
                <p className="text-xs text-muted-foreground">Errors before</p>
              </CardContent></Card>
              <Card className="dashboard-card"><CardContent className="pt-4 text-center">
                <p className="text-2xl font-bold text-warning">+{analysis.diff.count_increase}</p>
                <p className="text-xs text-muted-foreground">Increase</p>
              </CardContent></Card>
              <Card className="dashboard-card"><CardContent className="pt-4 text-center">
                <p className="text-2xl font-bold text-primary">{analysis.diff.new_pattern_count}</p>
                <p className="text-xs text-muted-foreground">New patterns</p>
              </CardContent></Card>
            </div>
          </motion.div>

          {/* Code Correlation */}
          {analysis.code_correlation?.length > 0 && (
            <motion.div variants={itemVariants}>
              <Card className="dashboard-card">
                <CardHeader className="pb-3">
                  <CardTitle className="text-base flex items-center gap-2">
                    <div className="p-1.5 bg-primary/10 rounded"><Code className="h-4 w-4 text-primary" /></div>
                    Code Correlation
                  </CardTitle>
                  <CardDescription>Errors mapped to potentially responsible code</CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  {analysis.code_correlation.map((corr: any, i: number) => (
                    <div key={i} className="p-3 border border-border rounded-lg">
                      <div className="flex items-start gap-2 mb-2">
                        <AlertTriangle className="h-3.5 w-3.5 mt-0.5 text-destructive flex-shrink-0" />
                        <p className="text-xs font-mono text-destructive/80 break-all">{corr.error_pattern}</p>
                      </div>
                      <div className="flex items-center gap-2 mb-1">
                        <ArrowRight className="h-3 w-3 text-muted-foreground" />
                        <span className="text-xs font-mono text-primary">{corr.related_file}</span>
                        <Badge variant="outline" className="text-[10px]">{Math.round(corr.relevance * 100)}% match</Badge>
                      </div>
                      <pre className="text-[11px] text-muted-foreground bg-muted/30 p-2 rounded mt-1 overflow-x-auto">{corr.code_snippet}</pre>
                    </div>
                  ))}
                </CardContent>
              </Card>
            </motion.div>
          )}

          {/* Side-by-side Log Diff */}
          <motion.div variants={itemVariants}>
            <Card className="dashboard-card">
              <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center gap-2">
                  <Terminal className="h-4 w-4" />
                  Log Diff — Side by Side
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                  <div>
                    <div className="flex items-center gap-2 mb-2">
                      <CheckCircle className="h-3.5 w-3.5 text-success" />
                      <span className="text-xs font-medium text-success">Healthy</span>
                    </div>
                    <div className="bg-muted/20 rounded-lg p-3 max-h-60 overflow-y-auto font-mono text-[11px] space-y-0.5">
                      {analysis.healthy_logs.length > 0 ? analysis.healthy_logs.map((log: any, i: number) => (
                        <div key={i} className="flex gap-2">
                          <span className="text-muted-foreground whitespace-nowrap">{log.timestamp?.slice(11, 19)}</span>
                          <span className="text-foreground/70 break-all">{log.message}</span>
                        </div>
                      )) : <p className="text-muted-foreground italic">No errors in healthy window</p>}
                    </div>
                  </div>
                  <div>
                    <div className="flex items-center gap-2 mb-2">
                      <AlertTriangle className="h-3.5 w-3.5 text-destructive" />
                      <span className="text-xs font-medium text-destructive">Error State</span>
                    </div>
                    <div className="bg-destructive/5 rounded-lg p-3 max-h-60 overflow-y-auto font-mono text-[11px] space-y-0.5">
                      {analysis.error_logs.length > 0 ? analysis.error_logs.map((log: any, i: number) => (
                        <div key={i} className="flex gap-2">
                          <span className="text-muted-foreground whitespace-nowrap">{log.timestamp?.slice(11, 19)}</span>
                          <span className="text-destructive/80 break-all">{log.message}</span>
                        </div>
                      )) : <p className="text-muted-foreground italic">No errors detected</p>}
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          </motion.div>

          {/* New Patterns + Infra Changes */}
          <motion.div variants={itemVariants} className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {analysis.diff.new_error_patterns?.length > 0 && (
              <Card className="dashboard-card">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">New Error Patterns</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-1 max-h-40 overflow-y-auto">
                    {analysis.diff.new_error_patterns.slice(0, 8).map((p: string, i: number) => (
                      <div key={i} className="flex items-start gap-1.5 text-[11px] font-mono p-1 bg-destructive/5 rounded">
                        <ArrowRight className="h-3 w-3 mt-0.5 text-destructive flex-shrink-0" />
                        <span className="break-all">{p}</span>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}

            {analysis.infra_changes?.length > 0 && (
              <Card className="dashboard-card">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm flex items-center gap-2"><Clock className="h-4 w-4" />Infra Changes</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-1.5">
                    {analysis.infra_changes.map((c: any, i: number) => (
                      <div key={i} className="flex items-center justify-between text-xs p-1.5 bg-muted/20 rounded">
                        <Badge variant="secondary" className="text-[10px]">{c.event}</Badge>
                        <span className="text-muted-foreground">{c.user} · {c.time?.slice(11, 19)}</span>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}
          </motion.div>
        </motion.div>
      )}

      {analysis?.status === "error" && (
        <Card className="dashboard-card border-destructive/30">
          <CardContent className="pt-6 text-center">
            <AlertTriangle className="h-8 w-8 text-destructive mx-auto mb-2" />
            <p className="text-sm text-destructive">{analysis.error}</p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// ─── Main Page ─────────────────────────────────────────────────────────────

export function LogAnalyser() {
  return (
    <motion.div variants={containerVariants} initial="hidden" animate="visible" className="space-y-6">
      <motion.div variants={itemVariants}>
        <h1 className="text-3xl font-bold text-foreground">Engineering Intelligence</h1>
        <p className="text-muted-foreground mt-2">
          Code + Infrastructure reasoning — understand PRs and production incidents with full context
        </p>
      </motion.div>

      <motion.div variants={itemVariants}>
        <Tabs defaultValue="pr" className="w-full">
          <TabsList className="grid w-full grid-cols-2 max-w-md">
            <TabsTrigger value="pr" className="gap-2">
              <GitPullRequest className="h-4 w-4" />PR Intelligence
            </TabsTrigger>
            <TabsTrigger value="logs" className="gap-2">
              <Terminal className="h-4 w-4" />Log Intelligence
            </TabsTrigger>
          </TabsList>

          <TabsContent value="pr" className="mt-5">
            <PRIntelligence />
          </TabsContent>

          <TabsContent value="logs" className="mt-5">
            <LogIntelligence />
          </TabsContent>
        </Tabs>
      </motion.div>
    </motion.div>
  );
}

import { useState, useEffect, useMemo } from "react";
import { motion } from "framer-motion";
import { Clock, CheckCircle, AlertTriangle, Activity, FileText, Lightbulb, RefreshCw } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { useToast } from "@/hooks/use-toast";

const API = "http://localhost:8000";

const itemVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: { opacity: 1, y: 0 }
};

// Backend types (mirrors services/incidents.py + correlation.py)
type IncidentSummary = {
  incident_id: string;
  status: string;
  severity: string;
  created_at: string;
  member_alert_ids: string[];
  resources_affected: string[];
  title: string;
  source_count?: number;
};

type TimelineEvent = {
  id: string;
  timestamp: string;
  type: string;
  source?: string;
  message: string;
  severity: string;
};

type IncidentDetail = {
  incident_id: string;
  timeline: TimelineEvent[];
  rootCause: any | null;     // populated by LLM agent in step 3
  checklist: any[];          // populated by LLM agent in step 3
  generated_at: string;
};

export function IncidentCoordinator() {
  const [incidents, setIncidents] = useState<IncidentSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<IncidentDetail | null>(null);
  const [loadingList, setLoadingList] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [checklist, setChecklist] = useState<any[]>([]);
  const [incidentResolved, setIncidentResolved] = useState(false);
  const { toast } = useToast();

  // ----- data loading -----------------------------------------------------

  const loadIncidents = async (autoSelect = true) => {
    setLoadingList(true);
    try {
      const res = await fetch(`${API}/incident`);
      if (!res.ok) throw new Error(`Backend returned ${res.status}`);
      const data: IncidentSummary[] = await res.json();
      setIncidents(data);
      if (autoSelect && data.length > 0 && !selectedId) {
        setSelectedId(data[0].incident_id);
      }
    } catch (err) {
      console.error("Failed to load incidents:", err);
      toast({ title: "Couldn't load incidents", description: String(err), variant: "destructive" });
    } finally {
      setLoadingList(false);
    }
  };

  const loadDetail = async (id: string) => {
    setLoadingDetail(true);
    try {
      const res = await fetch(`${API}/incident/${id}`);
      if (!res.ok) throw new Error(`Backend returned ${res.status}`);
      const data: IncidentDetail = await res.json();
      setDetail(data);
      // Local checklist state (LLM step will hydrate this; placeholder for now).
      setChecklist(data.checklist ?? []);
      setIncidentResolved(false);
    } catch (err) {
      console.error("Failed to load incident detail:", err);
      toast({ title: "Couldn't load incident", description: String(err), variant: "destructive" });
    } finally {
      setLoadingDetail(false);
    }
  };

  const runAnalysis = async (force = false) => {
    if (!selectedId) return;
    setAnalyzing(true);
    try {
      const res = await fetch(`${API}/incident/${selectedId}/analyze${force ? "?force=true" : ""}`, {
        method: "POST",
      });
      if (!res.ok) {
        const body = await res.text();
        throw new Error(body || `Backend returned ${res.status}`);
      }
      // Re-fetch detail so cached analysis flows back into the UI.
      await loadDetail(selectedId);
      toast({ title: "Analysis ready", description: "Root cause + mitigation checklist generated." });
    } catch (err) {
      console.error("Analysis failed:", err);
      toast({ title: "Analysis failed", description: String(err), variant: "destructive" });
    } finally {
      setAnalyzing(false);
    }
  };

  const refreshCorrelation = async () => {
    setRefreshing(true);
    try {
      const res = await fetch(`${API}/incident/refresh`, { method: "POST" });
      if (!res.ok) throw new Error(`Backend returned ${res.status}`);
      const fresh: IncidentSummary[] = await res.json();
      setIncidents(fresh);
      toast({ title: "Correlation refreshed", description: `Found ${fresh.length} incident(s).` });
      if (fresh.length > 0) {
        setSelectedId(fresh[0].incident_id);
      } else {
        setSelectedId(null);
        setDetail(null);
      }
    } catch (err) {
      console.error("Refresh failed:", err);
      toast({ title: "Refresh failed", description: String(err), variant: "destructive" });
    } finally {
      setRefreshing(false);
    }
  };

  useEffect(() => {
    loadIncidents();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (selectedId) loadDetail(selectedId);
  }, [selectedId]);

  // ----- helpers ----------------------------------------------------------

  const selectedSummary = useMemo(
    () => incidents.find(i => i.incident_id === selectedId) ?? null,
    [incidents, selectedId]
  );

  const getSeverityColor = (severity: string) => {
    switch ((severity || "").toLowerCase()) {
      case "critical": return "status-critical";
      case "high":
      case "warning": return "status-warning";
      default: return "bg-muted text-muted-foreground";
    }
  };

  const getEventIcon = (type: string) => {
    switch (type) {
      case "Alert": return <AlertTriangle className="h-4 w-4" />;
      case "Action": return <Activity className="h-4 w-4" />;
      case "Log": return <FileText className="h-4 w-4" />;
      default: return <Clock className="h-4 w-4" />;
    }
  };

  const handleChecklistToggle = (taskId: string) => {
    setChecklist(prev => prev.map(item =>
      item.id === taskId ? { ...item, completed: !item.completed } : item
    ));
  };

  const handleResolveIncident = () => {
    setIncidentResolved(true);
    toast({ title: "🎉 Incident Resolved!", description: "Generating summary report." });
  };

  const completedTasks = checklist.filter(item => item.completed).length;
  const progressPercentage = checklist.length > 0 ? (completedTasks / checklist.length) * 100 : 0;

  // ----- render -----------------------------------------------------------

  if (loadingList) {
    return <div className="text-center text-muted-foreground">Loading incidents...</div>;
  }

  return (
    <div className="space-y-6">
      {/* Incident picker */}
      <motion.div variants={itemVariants}>
        <Card className="dashboard-card">
          <CardHeader>
            <CardTitle className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <AlertTriangle className="h-5 w-5 text-primary" />
                <span>Active Incidents</span>
                <Badge variant="outline">{incidents.length}</Badge>
              </div>
              <Button
                size="sm"
                variant="outline"
                onClick={refreshCorrelation}
                disabled={refreshing}
              >
                <RefreshCw className={`h-4 w-4 mr-2 ${refreshing ? "animate-spin" : ""}`} />
                {refreshing ? "Correlating..." : "Re-run correlation"}
              </Button>
            </CardTitle>
            <CardDescription>
              Alerts grouped into incidents by resource overlap and time window.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {incidents.length === 0 ? (
              <div className="text-sm text-muted-foreground py-4 text-center">
                No incidents yet. Click <strong>Re-run correlation</strong> to build them from current alerts.
              </div>
            ) : (
              <div className="space-y-2">
                {incidents.map(inc => (
                  <button
                    key={inc.incident_id}
                    onClick={() => setSelectedId(inc.incident_id)}
                    className={`w-full text-left p-3 rounded-lg border transition-colors ${
                      inc.incident_id === selectedId
                        ? "border-primary bg-primary/5"
                        : "border-border hover:bg-muted/40"
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center space-x-2">
                        <Badge className={getSeverityColor(inc.severity)}>
                          {inc.severity}
                        </Badge>
                        <span className="text-sm font-medium">{inc.title}</span>
                      </div>
                      <span className="text-xs text-muted-foreground font-mono">
                        {inc.incident_id}
                      </span>
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {inc.member_alert_ids.length} alert(s) · {inc.resources_affected.length} resource(s) ·{" "}
                      {new Date(inc.created_at).toLocaleString()}
                    </div>
                  </button>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </motion.div>

      {/* Detail view */}
      {!selectedId ? null : loadingDetail || !detail ? (
        <div className="text-center text-muted-foreground">Loading incident detail...</div>
      ) : (
        <>
          {/* Incident Timeline */}
          <motion.div variants={itemVariants}>
            <Card className="dashboard-card">
              <CardHeader>
                <CardTitle className="flex items-center space-x-2">
                  <Clock className="h-5 w-5 text-primary" />
                  <span>Incident Timeline</span>
                  {selectedSummary && (
                    <Badge variant="outline" className="ml-2">
                      {selectedSummary.incident_id}
                    </Badge>
                  )}
                </CardTitle>
                <CardDescription>
                  Chronological view of correlated events, logs, and actions
                </CardDescription>
              </CardHeader>
              <CardContent>
                {detail.timeline.length === 0 ? (
                  <div className="text-sm text-muted-foreground py-4">
                    No events recorded for this incident yet.
                  </div>
                ) : (
                  <div className="relative">
                    <div className="absolute left-6 top-0 bottom-0 w-px bg-border"></div>
                    <div className="space-y-6">
                      {detail.timeline.map((event, index) => (
                        <motion.div
                          key={event.id}
                          initial={{ opacity: 0, x: -20 }}
                          animate={{ opacity: 1, x: 0 }}
                          transition={{ delay: index * 0.1 }}
                          className="relative flex items-start space-x-4"
                        >
                          <div className="flex items-center justify-center w-12 h-12 bg-background border-2 border-border rounded-full z-10">
                            {getEventIcon(event.type)}
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center space-x-2 mb-1">
                              <Badge variant="outline" className="text-xs">{event.type}</Badge>
                              <Badge className={getSeverityColor(event.severity)}>
                                {event.severity}
                              </Badge>
                              <span className="text-xs text-muted-foreground">
                                {event.timestamp ? new Date(event.timestamp).toLocaleTimeString() : ""}
                              </span>
                            </div>
                            <p className="text-sm font-medium text-foreground">{event.message}</p>
                            {event.source && (
                              <p className="text-xs text-muted-foreground">{event.source}</p>
                            )}
                          </div>
                        </motion.div>
                      ))}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          </motion.div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Root Cause Analysis (LLM-generated; placeholder until step 3) */}
            <motion.div variants={itemVariants}>
              <Card className="dashboard-card">
                <CardHeader>
                  <CardTitle className="flex items-center space-x-2">
                    <Lightbulb className="h-5 w-5 text-warning" />
                    <span>AI Root Cause Analysis</span>
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {detail.rootCause ? (
                    <div className="space-y-4">
                      {detail.rootCause.primaryCause && (
                        <div className="p-4 bg-primary/5 border border-primary/20 rounded-lg">
                          <h4 className="font-medium text-foreground mb-2">Primary Cause</h4>
                          <p className="text-sm text-muted-foreground">
                            {detail.rootCause.primaryCause}
                          </p>
                        </div>
                      )}
                      {Array.isArray(detail.rootCause.contributingFactors) && (
                        <div className="p-4 bg-warning/5 border border-warning/20 rounded-lg">
                          <h4 className="font-medium text-foreground mb-2">Contributing Factors</h4>
                          <ul className="text-sm text-muted-foreground space-y-1">
                            {detail.rootCause.contributingFactors.map((f: string, i: number) => (
                              <li key={i}>• {f}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {Array.isArray(detail.rootCause.immediateActions) && (
                        <div className="p-4 bg-success/5 border border-success/20 rounded-lg">
                          <h4 className="font-medium text-foreground mb-2">Immediate Actions</h4>
                          <ul className="text-sm text-muted-foreground space-y-1">
                            {detail.rootCause.immediateActions.map((a: string, i: number) => (
                              <li key={i}>• {a}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {detail.rootCause.confidence != null && (
                        <div className="text-xs text-muted-foreground text-right">
                          AI Confidence Score:{" "}
                          <span className="font-semibold text-primary">
                            {detail.rootCause.confidence}%
                          </span>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="p-4 border border-dashed border-border rounded-lg text-sm text-muted-foreground space-y-3">
                      <div>
                        <Lightbulb className="h-5 w-5 inline mr-2 text-warning" />
                        No analysis yet for this incident.
                      </div>
                      <Button size="sm" onClick={() => runAnalysis(false)} disabled={analyzing}>
                        <RefreshCw className={`h-4 w-4 mr-2 ${analyzing ? "animate-spin" : ""}`} />
                        {analyzing ? "Analyzing with Claude..." : "Generate analysis"}
                      </Button>
                    </div>
                  )}
                  {detail.rootCause && (
                    <div className="mt-4 text-right">
                      <Button size="sm" variant="ghost" onClick={() => runAnalysis(true)} disabled={analyzing}>
                        <RefreshCw className={`h-3 w-3 mr-2 ${analyzing ? "animate-spin" : ""}`} />
                        Re-analyze
                      </Button>
                    </div>
                  )}
                </CardContent>
              </Card>
            </motion.div>

            {/* Mitigation Checklist (also LLM-generated) */}
            <motion.div variants={itemVariants}>
              <Card className="dashboard-card">
                <CardHeader>
                  <CardTitle className="flex items-center justify-between">
                    <div className="flex items-center space-x-2">
                      <CheckCircle className="h-5 w-5 text-success" />
                      <span>Mitigation Checklist</span>
                    </div>
                    <span className="text-sm text-muted-foreground">
                      {completedTasks}/{checklist.length} completed
                    </span>
                  </CardTitle>
                  {checklist.length > 0 && (
                    <div className="mt-2">
                      <div className="w-full bg-muted rounded-full h-2">
                        <motion.div
                          className="bg-success h-2 rounded-full"
                          initial={{ width: 0 }}
                          animate={{ width: `${progressPercentage}%` }}
                          transition={{ duration: 0.5 }}
                        />
                      </div>
                    </div>
                  )}
                </CardHeader>
                <CardContent>
                  {checklist.length === 0 ? (
                    <div className="p-4 border border-dashed border-border rounded-lg text-sm text-muted-foreground">
                      The mitigation checklist is generated alongside the root cause.
                      Click <strong>Generate analysis</strong> on the left.
                    </div>
                  ) : (
                    <>
                      <div className="space-y-3">
                        {checklist.map(item => (
                          <div key={item.id} className="flex items-center space-x-3">
                            <Checkbox
                              checked={item.completed}
                              onCheckedChange={() => handleChecklistToggle(item.id)}
                            />
                            <span className={`text-sm ${item.completed ? "line-through text-muted-foreground" : "text-foreground"}`}>
                              {item.task}
                            </span>
                          </div>
                        ))}
                      </div>
                      <div className="mt-6">
                        {!incidentResolved ? (
                          <Button
                            onClick={handleResolveIncident}
                            disabled={completedTasks < checklist.length}
                            className="w-full action-success"
                          >
                            <CheckCircle className="h-4 w-4 mr-2" />
                            Mark Incident as Resolved
                          </Button>
                        ) : (
                          <div className="space-y-4 text-center p-4 bg-success/5 border border-success/20 rounded-lg">
                            <div>
                              <CheckCircle className="h-8 w-8 text-success mx-auto mb-2" />
                              <p className="font-medium text-success">Incident Resolved</p>
                              <p className="text-sm text-muted-foreground">
                                Your post-incident report is ready.
                              </p>
                            </div>
                            <Button
                              onClick={() => window.open(`${API}/incident/report`, "_blank")}
                              className="w-full"
                              variant="outline"
                            >
                              <FileText className="h-4 w-4 mr-2" />
                              Download Incident Report (PDF)
                            </Button>
                          </div>
                        )}
                      </div>
                    </>
                  )}
                </CardContent>
              </Card>
            </motion.div>
          </div>
        </>
      )}
    </div>
  );
}

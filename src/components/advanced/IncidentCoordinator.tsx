import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { Clock, CheckCircle, AlertTriangle, Activity, FileText, Lightbulb } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { useToast } from "@/hooks/use-toast";

const itemVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: { opacity: 1, y: 0 }
};

export function IncidentCoordinator() {
  const [timeline, setTimeline] = useState<any[]>([]);
  const [rootCause, setRootCause] = useState<any>(null);
  const [checklist, setChecklist] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [incidentResolved, setIncidentResolved] = useState(false);
  const { toast } = useToast();

  useEffect(() => {
    fetchIncidentData();
  }, []);

  const fetchIncidentData = async () => {
    try {
      console.log("🔄 Fetching incident data from backend...");
      const response = await fetch("http://localhost:8000/incident/data");
      
      if (!response.ok) {
        throw new Error(`Backend returned ${response.status}`);
      }
      
      const data = await response.json();
      console.log("✅ Successfully fetched incident data:", data);
      setTimeline(data.timeline);
      setRootCause(data.rootCause);
      setChecklist(data.checklist);
    } catch (error) {
      console.error("❌ Failed to fetch incident data:", error);
      // Fallback to empty data
      setTimeline([]);
      setRootCause(null);
      setChecklist([]);
    } finally {
      setLoading(false);
    }
  };

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case 'Critical': return 'status-critical';
      case 'Warning': return 'status-warning';
      default: return 'bg-muted text-muted-foreground';
    }
  };

  const getEventIcon = (type: string) => {
    switch (type) {
      case 'Alert': return <AlertTriangle className="h-4 w-4" />;
      case 'Action': return <Activity className="h-4 w-4" />;
      case 'Log': return <FileText className="h-4 w-4" />;
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
    toast({
      title: "🎉 Incident Resolved!",
      description: "Generating comic-strip postmortem summary...",
    });
    
    // Auto-generate postmortem after a short delay
    setTimeout(() => {
      toast({
        title: "📚 Postmortem Ready",
        description: "Your comic-strip incident summary has been generated and shared with the team.",
      });
    }, 2000);
  };

  const completedTasks = checklist.filter(item => item.completed).length;
  const progressPercentage = checklist.length > 0 ? (completedTasks / checklist.length) * 100 : 0;

  if (loading) {
    return <div className="text-center text-muted-foreground">Loading incident data...</div>;
  }

  return (
    <div className="space-y-6">
      {/* Incident Timeline */}
      <motion.div variants={itemVariants}>
        <Card className="dashboard-card">
          <CardHeader>
            <CardTitle className="flex items-center space-x-2">
              <Clock className="h-5 w-5 text-primary" />
              <span>Incident Timeline</span>
            </CardTitle>
            <CardDescription>
              Chronological view of correlated events, logs, and actions
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="relative">
              {/* Timeline line */}
              <div className="absolute left-6 top-0 bottom-0 w-px bg-border"></div>
              
              <div className="space-y-6">
                {timeline.map((event, index) => (
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
                          {new Date(event.timestamp).toLocaleTimeString()}
                        </span>
                      </div>
                      <p className="text-sm font-medium text-foreground">{event.message}</p>
                      <p className="text-xs text-muted-foreground">{event.source}</p>
                    </div>
                  </motion.div>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>
      </motion.div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Root Cause Analysis */}
        <motion.div variants={itemVariants}>
          <Card className="dashboard-card">
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <Lightbulb className="h-5 w-5 text-warning" />
                <span>AI Root Cause Analysis</span>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <div className="p-4 bg-primary/5 border border-primary/20 rounded-lg">
                  <h4 className="font-medium text-foreground mb-2">Primary Cause</h4>
                  <p className="text-sm text-muted-foreground">
                    Database connection pool exhaustion due to inefficient query patterns 
                    combined with high traffic load during peak hours.
                  </p>
                </div>
                
                <div className="p-4 bg-warning/5 border border-warning/20 rounded-lg">
                  <h4 className="font-medium text-foreground mb-2">Contributing Factors</h4>
                  <ul className="text-sm text-muted-foreground space-y-1">
                    <li>• Auto-scaling threshold set too high (80% CPU)</li>
                    <li>• Missing connection pool monitoring</li>
                    <li>• Inefficient database queries (N+1 problem)</li>
                  </ul>
                </div>

                <div className="p-4 bg-success/5 border border-success/20 rounded-lg">
                  <h4 className="font-medium text-foreground mb-2">Immediate Actions</h4>
                  <ul className="text-sm text-muted-foreground space-y-1">
                    <li>✓ Scaled web servers from 2 to 4 instances</li>
                    <li>✓ Increased database connection pool size</li>
                    <li>✓ Applied query optimization patches</li>
                  </ul>
                </div>
              </div>
            </CardContent>
          </Card>
        </motion.div>

        {/* Mitigation Checklist */}
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
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {checklist.map((item) => (
                  <div key={item.id} className="flex items-center space-x-3">
                    <Checkbox
                      checked={item.completed}
                      onCheckedChange={() => handleChecklistToggle(item.id)}
                    />
                    <span className={`text-sm ${item.completed ? 'line-through text-muted-foreground' : 'text-foreground'}`}>
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
                  <div className="text-center p-4 bg-success/5 border border-success/20 rounded-lg">
                    <CheckCircle className="h-8 w-8 text-success mx-auto mb-2" />
                    <p className="font-medium text-success">Incident Resolved</p>
                    <p className="text-sm text-muted-foreground">
                      🎨 Comic-strip postmortem generated and shared
                    </p>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        </motion.div>
      </div>

      {/* Comic Strip Postmortem Preview */}
      {incidentResolved && (
        <motion.div
          variants={itemVariants}
          initial="hidden"
          animate="visible"
        >
          <Card className="dashboard-card">
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <FileText className="h-5 w-5 text-primary" />
                <span>Comic-Strip Postmortem</span>
              </CardTitle>
              <CardDescription>
                Auto-generated visual incident summary for team sharing
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-4 gap-4">
                <div className="p-4 border-2 border-dashed border-primary/20 rounded-lg text-center">
                  <div className="w-16 h-16 bg-critical/10 rounded-full mx-auto mb-2 flex items-center justify-center">
                    <AlertTriangle className="h-8 w-8 text-critical" />
                  </div>
                  <p className="text-xs font-medium">1. Incident Start</p>
                  <p className="text-xs text-muted-foreground">High CPU detected</p>
                </div>
                
                <div className="p-4 border-2 border-dashed border-primary/20 rounded-lg text-center">
                  <div className="w-16 h-16 bg-warning/10 rounded-full mx-auto mb-2 flex items-center justify-center">
                    <Activity className="h-8 w-8 text-warning" />
                  </div>
                  <p className="text-xs font-medium">2. Investigation</p>
                  <p className="text-xs text-muted-foreground">Root cause found</p>
                </div>
                
                <div className="p-4 border-2 border-dashed border-primary/20 rounded-lg text-center">
                  <div className="w-16 h-16 bg-primary/10 rounded-full mx-auto mb-2 flex items-center justify-center">
                    <Clock className="h-8 w-8 text-primary" />
                  </div>
                  <p className="text-xs font-medium">3. Mitigation</p>
                  <p className="text-xs text-muted-foreground">Auto-scaling applied</p>
                </div>
                
                <div className="p-4 border-2 border-dashed border-success/20 rounded-lg text-center">
                  <div className="w-16 h-16 bg-success/10 rounded-full mx-auto mb-2 flex items-center justify-center">
                    <CheckCircle className="h-8 w-8 text-success" />
                  </div>
                  <p className="text-xs font-medium">4. Resolution</p>
                  <p className="text-xs text-muted-foreground">Service restored</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </motion.div>
      )}
    </div>
  );
}
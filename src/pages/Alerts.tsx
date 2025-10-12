import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { AlertTriangle, CheckCircle, Clock, Filter, X } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Alert } from "@/lib/mockData";
import { useToast } from "@/hooks/use-toast";
import { IncidentCoordinator } from "@/components/advanced/IncidentCoordinator";
// Removed Supabase import - now using FastAPI

const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.05
    }
  }
};

const itemVariants = {
  hidden: { opacity: 0, x: -20 },
  visible: { opacity: 1, x: 0 }
};

export function Alerts() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [selectedAlert, setSelectedAlert] = useState<Alert | null>(null);
  const [filter, setFilter] = useState<"All" | "Critical" | "Warning" | "Info">("All");
  const [loading, setLoading] = useState(true);
  const { toast } = useToast();

  // Fetch alerts from FastAPI backend
  useEffect(() => {
    const fetchAlerts = async () => {
      try {
        setLoading(true);
        const response = await fetch('http://localhost:8000/alerts');
        
        if (!response.ok) throw new Error('Failed to fetch alerts');
        
        const data = await response.json();
        setAlerts(data);
      } catch (error) {
        console.error('Error fetching alerts:', error);
        toast({
          title: "Error Loading Alerts",
          description: "Failed to fetch alerts. Make sure FastAPI server is running on localhost:8000",
          variant: "destructive"
        });
      } finally {
        setLoading(false);
      }
    };

    fetchAlerts();
  }, [toast]);

  const filteredAlerts = alerts.filter(alert => 
    filter === "All" || alert.severity === filter
  );

  const handleApplyFix = async (alertId: string) => {
    try {
      const alert = alerts.find(a => a.id === alertId);
      
      // Call FastAPI backend to update alert status
      const response = await fetch(`http://localhost:8000/alerts/${alertId}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ status: 'resolved' }),
      });

      if (!response.ok) throw new Error('Failed to update alert');

      // Update local state
      setAlerts(prev => prev.map(a => 
        a.id === alertId 
          ? { ...a, status: "Resolved" as const }
          : a
      ));
      
      toast({
        title: "Fix Applied Successfully",
        description: `${alert?.title} has been resolved${alert?.estimatedSavings ? ` with $${alert.estimatedSavings}/month savings` : ''}`,
      });
      
      setSelectedAlert(null);
    } catch (error) {
      console.error('Error applying fix:', error);
      toast({
        title: "Error",
        description: "Failed to apply fix",
        variant: "destructive"
      });
    }
  };

  const handleDismiss = async (alertId: string) => {
    try {
      // Call FastAPI backend to delete alert
      const response = await fetch(`http://localhost:8000/alerts/${alertId}`, {
        method: 'DELETE',
      });

      if (!response.ok) throw new Error('Failed to delete alert');

      // Update local state
      setAlerts(prev => prev.filter(a => a.id !== alertId));
      
      toast({
        title: "Alert Dismissed",
        description: "Alert has been removed",
      });
      
      setSelectedAlert(null);
    } catch (error) {
      console.error('Error dismissing alert:', error);
      toast({
        title: "Error",
        description: "Failed to dismiss alert",
        variant: "destructive"
      });
    }
  };

  const getSeverityColor = (severity: Alert['severity']) => {
    switch (severity) {
      case 'Critical': return 'status-critical';
      case 'Warning': return 'status-warning';
      case 'Info': return 'bg-muted text-muted-foreground';
      default: return 'bg-muted text-muted-foreground';
    }
  };

  const getStatusIcon = (status: Alert['status']) => {
    switch (status) {
      case 'Resolved': return <CheckCircle className="h-4 w-4 text-success" />;
      case 'In Progress': return <Clock className="h-4 w-4 text-warning" />;
      default: return <AlertTriangle className="h-4 w-4 text-critical" />;
    }
  };

  return (
    <motion.div
      variants={containerVariants}
      initial="hidden"
      animate="visible"
      className="space-y-6"
    >
      {/* Header */}
      <motion.div variants={itemVariants} className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-foreground">Alert Management</h1>
          <p className="text-muted-foreground mt-2">
            Monitor and resolve infrastructure alerts with AI recommendations
          </p>
        </div>
        
        <div className="flex items-center space-x-3">
          <div className="flex items-center space-x-2">
            <Filter className="h-4 w-4 text-muted-foreground" />
            <div className="flex space-x-1">
              {["All", "Critical", "Warning", "Info"].map((f) => (
                <Button
                  key={f}
                  variant={filter === f ? "default" : "ghost"}
                  size="sm"
                  onClick={() => setFilter(f as any)}
                  className="text-xs"
                >
                  {f}
                </Button>
              ))}
            </div>
          </div>
        </div>
      </motion.div>

      {/* Summary Cards */}
      <motion.div variants={itemVariants} className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card className="metric-card">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div className="space-y-1">
                <p className="text-sm text-muted-foreground">Critical</p>
                <p className="text-2xl font-bold text-critical">
                  {alerts.filter(a => a.severity === 'Critical' && a.status === 'Active').length}
                </p>
              </div>
              <AlertTriangle className="h-8 w-8 text-critical" />
            </div>
          </CardContent>
        </Card>

        <Card className="metric-card">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div className="space-y-1">
                <p className="text-sm text-muted-foreground">Warning</p>
                <p className="text-2xl font-bold text-warning">
                  {alerts.filter(a => a.severity === 'Warning' && a.status === 'Active').length}
                </p>
              </div>
              <AlertTriangle className="h-8 w-8 text-warning" />
            </div>
          </CardContent>
        </Card>

        <Card className="metric-card">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div className="space-y-1">
                <p className="text-sm text-muted-foreground">Resolved</p>
                <p className="text-2xl font-bold text-success">
                  {alerts.filter(a => a.status === 'Resolved').length}
                </p>
              </div>
              <CheckCircle className="h-8 w-8 text-success" />
            </div>
          </CardContent>
        </Card>

        <Card className="metric-card">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div className="space-y-1">
                <p className="text-sm text-muted-foreground">In Progress</p>
                <p className="text-2xl font-bold text-primary">
                  {alerts.filter(a => a.status === 'In Progress').length}
                </p>
              </div>
              <Clock className="h-8 w-8 text-primary" />
            </div>
          </CardContent>
        </Card>
      </motion.div>

      {/* Alerts Table */}
      <motion.div variants={itemVariants}>
        <Card className="dashboard-card">
          <CardHeader>
            <CardTitle>Active Alerts</CardTitle>
            <CardDescription>
              Click on any alert to view details and apply AI-recommended fixes
            </CardDescription>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="flex items-center justify-center py-12">
                <div className="text-muted-foreground">Loading alerts...</div>
              </div>
            ) : filteredAlerts.length === 0 ? (
              <div className="flex items-center justify-center py-12">
                <div className="text-muted-foreground">No alerts found</div>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Alert</th>
                      <th>Type</th>
                      <th>Severity</th>
                      <th>Resource</th>
                      <th>Status</th>
                      <th>Potential Savings</th>
                      <th>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredAlerts.map((alert) => (
                    <motion.tr
                      key={alert.id}
                      variants={itemVariants}
                      className="cursor-pointer hover:bg-muted/50"
                      onClick={() => setSelectedAlert(alert)}
                    >
                      <td>
                        <div className="flex items-start space-x-3">
                          {getStatusIcon(alert.status)}
                          <div>
                            <p className="font-medium text-foreground">{alert.title}</p>
                            <p className="text-sm text-muted-foreground line-clamp-2">
                              {alert.description}
                            </p>
                          </div>
                        </div>
                      </td>
                      <td>
                        <Badge variant="outline">{alert.type}</Badge>
                      </td>
                      <td>
                        <Badge className={getSeverityColor(alert.severity)}>
                          {alert.severity}
                        </Badge>
                      </td>
                      <td>
                        <code className="text-sm bg-muted px-2 py-1 rounded">
                          {alert.resourceId}
                        </code>
                      </td>
                      <td>
                        <div className="flex items-center space-x-2">
                          {getStatusIcon(alert.status)}
                          <span className="text-sm">{alert.status}</span>
                        </div>
                      </td>
                      <td>
                        {alert.estimatedSavings ? (
                          <span className="font-medium text-success">
                            ${alert.estimatedSavings}/mo
                          </span>
                        ) : (
                          <span className="text-muted-foreground">Security Fix</span>
                        )}
                      </td>
                      <td>
                        <Button
                          size="sm"
                          variant={alert.status === 'Resolved' ? 'outline' : 'default'}
                          disabled={alert.status === 'Resolved'}
                          onClick={(e) => {
                            e.stopPropagation();
                            setSelectedAlert(alert);
                          }}
                        >
                          {alert.status === 'Resolved' ? 'Resolved' : 'View Details'}
                        </Button>
                      </td>
                    </motion.tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      </motion.div>

      {/* Alert Detail Sheet */}
      <Sheet open={!!selectedAlert} onOpenChange={(open) => !open && setSelectedAlert(null)}>
        <SheetContent className="w-[500px]">
          {selectedAlert && (
            <>
              <SheetHeader>
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-3">
                    {getStatusIcon(selectedAlert.status)}
                    <Badge className={getSeverityColor(selectedAlert.severity)}>
                      {selectedAlert.severity}
                    </Badge>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setSelectedAlert(null)}
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </div>
                <SheetTitle className="text-left">{selectedAlert.title}</SheetTitle>
                <SheetDescription className="text-left">
                  {selectedAlert.description}
                </SheetDescription>
              </SheetHeader>

              <div className="mt-6 space-y-6">
                {/* Alert Details */}
                <div className="space-y-4">
                  <div>
                    <label className="text-sm font-medium text-muted-foreground">Resource ID</label>
                    <p className="mt-1 font-mono text-sm bg-muted p-2 rounded">
                      {selectedAlert.resourceId}
                    </p>
                  </div>

                  <div>
                    <label className="text-sm font-medium text-muted-foreground">Alert Type</label>
                    <p className="mt-1 text-sm">{selectedAlert.type}</p>
                  </div>

                  <div>
                    <label className="text-sm font-medium text-muted-foreground">Detected</label>
                    <p className="mt-1 text-sm">
                      {new Date(selectedAlert.timestamp).toLocaleString()}
                    </p>
                  </div>

                  {selectedAlert.estimatedSavings && (
                    <div>
                      <label className="text-sm font-medium text-muted-foreground">
                        Potential Monthly Savings
                      </label>
                      <p className="mt-1 text-lg font-bold text-success">
                        ${selectedAlert.estimatedSavings}
                      </p>
                    </div>
                  )}
                </div>

                {/* AI Recommendation */}
                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">AI Recommendation</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <p className="text-sm text-foreground">{selectedAlert.suggestedAction}</p>
                  </CardContent>
                </Card>

                {/* Actions */}
                <div className="flex space-x-3">
                  {selectedAlert.status !== 'Resolved' ? (
                    <>
                      <Button
                        onClick={() => handleApplyFix(selectedAlert.id)}
                        className="flex-1 action-success"
                      >
                        Apply Fix
                      </Button>
                      <Button 
                        variant="outline" 
                        className="flex-1"
                        onClick={() => handleDismiss(selectedAlert.id)}
                      >
                        Dismiss
                      </Button>
                    </>
                  ) : (
                    <div className="flex items-center space-x-2 text-success">
                      <CheckCircle className="h-5 w-5" />
                      <span className="font-medium">Alert Resolved</span>
                    </div>
                  )}
                </div>
              </div>
            </>
          )}
        </SheetContent>
      </Sheet>

      {/* Advanced AI Features - Incident Coordinator Tab */}
      <Tabs defaultValue="alerts" className="mt-8">
        <TabsList className="grid w-full grid-cols-2">
          <TabsTrigger value="alerts">Active Alerts</TabsTrigger>
          <TabsTrigger value="incident-room">Incident Room</TabsTrigger>
        </TabsList>
        <TabsContent value="alerts" className="mt-4">
          {/* Current alerts content is already shown above */}
        </TabsContent>
        <TabsContent value="incident-room" className="mt-4">
          <IncidentCoordinator />
        </TabsContent>
      </Tabs>
    </motion.div>
  );
}
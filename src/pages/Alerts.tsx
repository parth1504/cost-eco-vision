import { useState } from "react";
import { motion } from "framer-motion";
import { AlertTriangle, CheckCircle, Clock, Filter, X } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { mockAlerts, Alert } from "@/lib/mockData";
import { useToast } from "@/hooks/use-toast";
import { IncidentCoordinator } from "@/components/advanced/IncidentCoordinator";

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
  const [alerts, setAlerts] = useState<Alert[]>(mockAlerts);
  const [selectedAlert, setSelectedAlert] = useState<Alert | null>(null);
  const [filter, setFilter] = useState<"All" | "Critical" | "Warning" | "Info">("All");
  const { toast } = useToast();

  const filteredAlerts = alerts.filter(alert => 
    filter === "All" || alert.severity === filter
  );

  const handleApplyFix = (alertId: string) => {
    setAlerts(prev => prev.map(alert => 
      alert.id === alertId 
        ? { ...alert, status: "Resolved" as const }
        : alert
    ));
    
    const alert = alerts.find(a => a.id === alertId);
    toast({
      title: "Fix Applied Successfully",
      description: `${alert?.title} has been resolved${alert?.estimatedSavings ? ` with $${alert.estimatedSavings}/month savings` : ''}`,
    });
    
    setSelectedAlert(null);
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
                      <Button variant="outline" className="flex-1">
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
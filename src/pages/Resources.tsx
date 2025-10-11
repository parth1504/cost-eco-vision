import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { Server, Database, HardDrive, Zap, BarChart3, DollarSign, TrendingUp, Settings2 } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Resource } from "@/lib/mockData";
import { useToast } from "@/hooks/use-toast";
import { InfraGuardian } from "@/components/advanced/InfraGuardian";
import { supabase } from "@/integrations/supabase/client";

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
  hidden: { opacity: 0, scale: 0.95 },
  visible: { opacity: 1, scale: 1 }
};

const getResourceIcon = (type: Resource['type']) => {
  switch (type) {
    case 'EC2': return Server;
    case 'RDS': return Database;
    case 'S3': return HardDrive;
    case 'Lambda': return Zap;
    default: return Server;
  }
};

const getStatusColor = (status: Resource['status']) => {
  switch (status) {
    case 'Running': return 'status-success';
    case 'Idle': return 'status-warning';
    case 'Stopped': return 'bg-muted text-muted-foreground';
    case 'Optimized': return 'status-eco';
    default: return 'bg-muted text-muted-foreground';
  }
};

export function Resources() {
  const [resources, setResources] = useState<Resource[]>([]);
  const [selectedResource, setSelectedResource] = useState<Resource | null>(null);
  const [loading, setLoading] = useState(true);
  const { toast } = useToast();

  // Fetch resources from backend
  useEffect(() => {
    const fetchResources = async () => {
      try {
        setLoading(true);
        const { data, error } = await supabase.functions.invoke('resources',{
          method: 'GET'
        });
        
        if (error) throw error;
        
        setResources(data || []);
      } catch (error) {
        console.error('Error fetching resources:', error);
        toast({
          title: "Error",
          description: "Failed to load resources",
          variant: "destructive",
        });
      } finally {
        setLoading(false);
      }
    };

    fetchResources();
  }, [toast]);

  const handleOptimize = async (resourceId: string, action: string) => {
    try {
      const resource = resources.find(r => r.id === resourceId);
      const savings = resource ? Math.round((resource.monthlyCost * 0.3)) : 0;

      // Call backend optimize endpoint
      const { data, error } = await supabase.functions.invoke(`resources/optimize/${resourceId}`, {
        method: 'POST',
      });
      
      if (error) throw error;

      // Update local state with optimized resource
      setResources(prev => prev.map(r => 
        r.id === resourceId ? data : r
      ));
      
      toast({
        title: "Optimization Applied",
        description: `${action} applied to ${resource?.name}. Estimated savings: $${savings}/month`,
      });
      
      setSelectedResource(null);
    } catch (error) {
      console.error('Error optimizing resource:', error);
      toast({
        title: "Error",
        description: "Failed to optimize resource",
        variant: "destructive",
      });
    }
  };

  const totalMonthlyCost = resources.reduce((sum, r) => sum + r.monthlyCost, 0);
  const runningResources = resources.filter(r => r.status === 'Running').length;
  const idleResources = resources.filter(r => r.status === 'Idle').length;
  const optimizedResources = resources.filter(r => r.status === 'Optimized').length;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-muted-foreground">Loading resources...</p>
      </div>
    );
  }

  return (
    <motion.div
      variants={containerVariants}
      initial="hidden"
      animate="visible"
      className="space-y-6"
    >
      {/* Header */}
      <motion.div variants={itemVariants}>
        <h1 className="text-3xl font-bold text-foreground">Resource Management</h1>
        <p className="text-muted-foreground mt-2">
          Monitor and optimize your cloud resources with AI-powered recommendations
        </p>
      </motion.div>

      {/* Summary Cards */}
      <motion.div variants={itemVariants} className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card className="metric-card">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div className="space-y-1">
                <p className="text-sm text-muted-foreground">Total Cost</p>
                <p className="text-2xl font-bold text-foreground">
                  ${totalMonthlyCost.toFixed(0)}
                </p>
                <p className="text-xs text-muted-foreground">/month</p>
              </div>
              <DollarSign className="h-8 w-8 text-primary" />
            </div>
          </CardContent>
        </Card>

        <Card className="metric-card">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div className="space-y-1">
                <p className="text-sm text-muted-foreground">Running</p>
                <p className="text-2xl font-bold text-success">{runningResources}</p>
              </div>
              <Server className="h-8 w-8 text-success" />
            </div>
          </CardContent>
        </Card>

        <Card className="metric-card">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div className="space-y-1">
                <p className="text-sm text-muted-foreground">Idle</p>
                <p className="text-2xl font-bold text-warning">{idleResources}</p>
              </div>
              <BarChart3 className="h-8 w-8 text-warning" />
            </div>
          </CardContent>
        </Card>

        <Card className="metric-card">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div className="space-y-1">
                <p className="text-sm text-muted-foreground">Optimized</p>
                <p className="text-2xl font-bold text-eco">{optimizedResources}</p>
              </div>
              <TrendingUp className="h-8 w-8 text-eco" />
            </div>
          </CardContent>
        </Card>
      </motion.div>

      {/* Resource Grid */}
      <motion.div variants={itemVariants}>
        <h2 className="text-xl font-semibold mb-4">Resource Overview</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {resources.map((resource) => {
            const IconComponent = getResourceIcon(resource.type);
            
            return (
              <motion.div
                key={resource.id}
                variants={itemVariants}
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
              >
                <Card 
                  className="dashboard-card cursor-pointer hover:shadow-lg transition-all duration-300"
                  onClick={() => setSelectedResource(resource)}
                >
                  <CardHeader className="pb-3">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center space-x-3">
                        <div className="p-2 bg-primary/10 rounded-lg">
                          <IconComponent className="h-5 w-5 text-primary" />
                        </div>
                        <div>
                          <CardTitle className="text-base">{resource.name}</CardTitle>
                          <CardDescription>{resource.type} • {resource.region}</CardDescription>
                        </div>
                      </div>
                      <Badge className={getStatusColor(resource.status)}>
                        {resource.status}
                      </Badge>
                    </div>
                  </CardHeader>
                  
                  <CardContent className="space-y-4">
                    {/* Utilization */}
                    <div>
                      <div className="flex justify-between text-sm mb-2">
                        <span className="text-muted-foreground">Utilization</span>
                        <span className="font-medium">{resource.utilization}%</span>
                      </div>
                      <Progress 
                        value={resource.utilization} 
                        className="h-2"
                      />
                    </div>

                    {/* Cost */}
                    <div className="flex justify-between items-center">
                      <span className="text-sm text-muted-foreground">Monthly Cost</span>
                      <span className="font-bold text-foreground">
                        ${resource.monthlyCost.toFixed(2)}
                      </span>
                    </div>

                    {/* Recommendations */}
                    {resource.recommendations.length > 0 && (
                      <div>
                        <p className="text-sm font-medium text-foreground mb-2">
                          {resource.recommendations.length} Recommendation{resource.recommendations.length !== 1 ? 's' : ''}
                        </p>
                        <p className="text-xs text-muted-foreground line-clamp-2">
                          {resource.recommendations[0]}
                        </p>
                      </div>
                    )}

                    {/* Action Button */}
                    <Button 
                      className="w-full mt-4"
                      variant={resource.status === 'Optimized' ? 'outline' : 'default'}
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelectedResource(resource);
                      }}
                    >
                      {resource.status === 'Optimized' ? 'View Details' : 'Optimize'}
                    </Button>
                  </CardContent>
                </Card>
              </motion.div>
            );
          })}
        </div>
      </motion.div>

      {/* Resource Detail Modal */}
      <Dialog open={!!selectedResource} onOpenChange={(open) => !open && setSelectedResource(null)}>
        <DialogContent className="max-w-2xl">
          {selectedResource && (
            <>
              <DialogHeader>
                <div className="flex items-center space-x-3">
                  <div className="p-2 bg-primary/10 rounded-lg">
                    {(() => {
                      const IconComponent = getResourceIcon(selectedResource.type);
                      return <IconComponent className="h-6 w-6 text-primary" />;
                    })()}
                  </div>
                  <div>
                    <DialogTitle>{selectedResource.name}</DialogTitle>
                    <DialogDescription>
                      {selectedResource.type} instance in {selectedResource.region}
                    </DialogDescription>
                  </div>
                </div>
              </DialogHeader>

              <div className="space-y-6">
                {/* Status and Metrics */}
                <div className="grid grid-cols-2 gap-4">
                  <Card>
                    <CardContent className="p-4">
                      <div className="text-center">
                        <p className="text-sm text-muted-foreground">Status</p>
                        <Badge className={`${getStatusColor(selectedResource.status)} mt-2`}>
                          {selectedResource.status}
                        </Badge>
                      </div>
                    </CardContent>
                  </Card>

                  <Card>
                    <CardContent className="p-4">
                      <div className="text-center">
                        <p className="text-sm text-muted-foreground">Monthly Cost</p>
                        <p className="text-2xl font-bold text-foreground mt-1">
                          ${selectedResource.monthlyCost.toFixed(2)}
                        </p>
                      </div>
                    </CardContent>
                  </Card>
                </div>

                {/* Utilization Chart */}
                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">Resource Utilization</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-3">
                      <div className="flex justify-between text-sm">
                        <span>CPU Utilization</span>
                        <span className="font-medium">{selectedResource.utilization}%</span>
                      </div>
                      <Progress value={selectedResource.utilization} className="h-3" />
                      
                      <div className="text-xs text-muted-foreground">
                        Last updated: {new Date(selectedResource.lastActivity).toLocaleString()}
                      </div>
                    </div>
                  </CardContent>
                </Card>

                {/* AI Recommendations */}
                <Card>
                  <CardHeader>
                    <CardTitle className="text-base flex items-center space-x-2">
                      <Settings2 className="h-4 w-4" />
                      <span>AI Recommendations</span>
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-3">
                      {selectedResource.recommendations.map((rec, index) => (
                        <div key={index} className="flex items-start space-x-3 p-3 bg-muted/30 rounded-lg">
                          <div className="h-2 w-2 bg-primary rounded-full mt-2 flex-shrink-0" />
                          <div className="flex-1">
                            <p className="text-sm font-medium text-foreground">{rec}</p>
                            <p className="text-xs text-muted-foreground mt-1">
                              Estimated savings: ${Math.round(selectedResource.monthlyCost * 0.3)}/month
                            </p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>

                {/* Actions */}
                <div className="flex space-x-3">
                  {selectedResource.status !== 'Optimized' ? (
                    <>
                      <Button
                        onClick={() => handleOptimize(selectedResource.id, "Right-sizing")}
                        className="flex-1 action-success"
                      >
                        Apply Optimization
                      </Button>
                      <Button variant="outline" className="flex-1">
                        Schedule Maintenance
                      </Button>
                    </>
                  ) : (
                    <div className="flex items-center justify-center space-x-2 text-eco py-2">
                      <TrendingUp className="h-5 w-5" />
                      <span className="font-medium">Resource Optimized</span>
                    </div>
                  )}
                </div>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>

      {/* Advanced AI Features */}
      <InfraGuardian />
    </motion.div>
  );
}
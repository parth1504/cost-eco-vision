import { useState } from "react";
import { motion } from "framer-motion";
import { Cloud, CloudRain, Sun, CloudSnow, Zap, TrendingUp } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { mockCapacityForecasts } from "@/lib/mockData";
import { useToast } from "@/hooks/use-toast";

const itemVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: { opacity: 1, y: 0 }
};

export function CapacityOracle() {
  const [autoScaleEnabled, setAutoScaleEnabled] = useState(false);
  const [forecasts] = useState(mockCapacityForecasts);
  const { toast } = useToast();

  const getWeatherIcon = (status: string, metric: string) => {
    if (status === "Critical") {
      return <CloudSnow className="h-6 w-6 text-critical" />;
    } else if (status === "Warning") {
      return <CloudRain className="h-6 w-6 text-warning" />;
    } else {
      return <Sun className="h-6 w-6 text-success" />;
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'Critical': return 'status-critical';
      case 'Warning': return 'status-warning';
      default: return 'status-success';
    }
  };

  const handleAutoScaleToggle = (enabled: boolean) => {
    setAutoScaleEnabled(enabled);
    
    if (enabled) {
      toast({
        title: "🤖 Auto-Scale Activated",
        description: "AI will automatically scale resources ahead of predicted demand spikes.",
      });
    } else {
      toast({
        title: "⏸️ Auto-Scale Paused",
        description: "Manual approval will be required for scaling actions.",
      });
    }
  };

  const potentialSavings = autoScaleEnabled ? 340 : 0;

  return (
    <div className="space-y-6">
      {/* Capacity Weather Dashboard */}
      <motion.div variants={itemVariants}>
        <Card className="dashboard-card">
          <CardHeader>
            <CardTitle className="flex items-center space-x-2">
              <Cloud className="h-5 w-5 text-primary" />
              <span>Capacity Weather Forecast</span>
            </CardTitle>
            <CardDescription>
              24-hour capacity predictions with weather-style visualization
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {forecasts.map((forecast, index) => (
                <motion.div
                  key={forecast.resource}
                  initial={{ opacity: 0, scale: 0.9 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ delay: index * 0.1 }}
                  className="p-4 border rounded-lg bg-gradient-to-br from-background to-muted/30"
                >
                  <div className="flex items-center justify-between mb-3">
                    <div>
                      <p className="font-medium text-foreground">{forecast.resource}</p>
                      <p className="text-sm text-muted-foreground">{forecast.metric}</p>
                    </div>
                    {getWeatherIcon(forecast.status, forecast.metric)}
                  </div>

                  <div className="space-y-3">
                    <div>
                      <div className="flex justify-between text-sm mb-1">
                        <span>Current</span>
                        <span>{forecast.current}%</span>
                      </div>
                      <Progress value={forecast.current} className="h-2" />
                    </div>

                    <div>
                      <div className="flex justify-between text-sm mb-1">
                        <span>Predicted</span>
                        <span className={forecast.predicted > 80 ? 'text-critical font-medium' : 'text-foreground'}>
                          {forecast.predicted}%
                        </span>
                      </div>
                      <Progress 
                        value={forecast.predicted} 
                        className={`h-2 ${forecast.predicted > 80 ? '[&>div]:bg-critical' : ''}`}
                      />
                    </div>

                    <div className="flex items-center justify-between pt-2">
                      <div>
                        <Badge className={getStatusColor(forecast.status)}>
                          {forecast.status}
                        </Badge>
                      </div>
                      <div className="text-right">
                        <p className="text-xs text-muted-foreground">{forecast.timeframe}</p>
                        <p className="text-xs font-medium">{forecast.confidence}% confidence</p>
                      </div>
                    </div>

                    {forecast.status !== "Normal" && (
                      <div className="mt-3 p-2 bg-warning/5 border border-warning/20 rounded text-xs">
                        {forecast.status === "Critical" ? 
                          `🌪️ ${forecast.metric} storm likely - scaling recommended` :
                          `⛅ ${forecast.metric} pressure building - monitor closely`
                        }
                      </div>
                    )}
                  </div>
                </motion.div>
              ))}
            </div>
          </CardContent>
        </Card>
      </motion.div>

      {/* Auto-Scale Control */}
      <motion.div variants={itemVariants}>
        <Card className="dashboard-card">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="flex items-center space-x-2">
                  <Zap className="h-5 w-5 text-success" />
                  <span>Predictive Auto-Scaling</span>
                </CardTitle>
                <CardDescription>
                  Scale resources ahead of predicted demand to prevent performance issues
                </CardDescription>
              </div>
              <Switch
                checked={autoScaleEnabled}
                onCheckedChange={handleAutoScaleToggle}
              />
            </div>
          </CardHeader>
          <CardContent>
            {autoScaleEnabled ? (
              <div className="space-y-4">
                <div className="p-4 bg-success/5 border border-success/20 rounded-lg">
                  <div className="flex items-center space-x-2 mb-2">
                    <Zap className="h-4 w-4 text-success" />
                    <span className="font-medium text-success">Auto-Scale Active</span>
                  </div>
                  <p className="text-sm text-muted-foreground mb-3">
                    AI will automatically scale resources 30 minutes before predicted demand spikes
                  </p>
                  
                  <div className="flex items-center justify-between">
                    <span className="text-sm">Projected monthly savings:</span>
                    <div className="flex items-center space-x-2">
                      <TrendingUp className="h-4 w-4 text-success" />
                      <span className="font-bold text-success">${potentialSavings}</span>
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                  <div>
                    <h4 className="font-medium mb-2">Scaling Triggers</h4>
                    <ul className="space-y-1 text-muted-foreground">
                      <li>• CPU {'>'}80% predicted</li>
                      <li>• Memory {'>'}85% predicted</li>
                      <li>• High confidence ({'>'}85%)</li>
                    </ul>
                  </div>
                  <div>
                    <h4 className="font-medium mb-2">Benefits</h4>
                    <ul className="space-y-1 text-muted-foreground">
                      <li>• Prevent performance degradation</li>
                      <li>• Optimize resource utilization</li>
                      <li>• Reduce manual intervention</li>
                    </ul>
                  </div>
                </div>
              </div>
            ) : (
              <div className="text-center py-6">
                <Cloud className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
                <p className="text-muted-foreground">
                  Enable predictive auto-scaling to optimize resource utilization and costs
                </p>
              </div>
            )}
          </CardContent>
        </Card>
      </motion.div>
    </div>
  );
}
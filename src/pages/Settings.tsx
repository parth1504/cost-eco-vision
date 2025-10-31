import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { Settings2, Bell, Mail, MessageSquare, Clock, Cloud, Shield, Save } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useToast } from "@/hooks/use-toast";

const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.1
    }
  }
};

const itemVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: { opacity: 1, y: 0 }
};

export function Settings() {
  const { toast } = useToast();
  
  // Notification Settings
  const [emailNotificationsEnabled, setEmailNotificationsEnabled] = useState(false);
  const [slackNotificationsEnabled, setSlackNotificationsEnabled] = useState(false);
  const [criticalAlertsEnabled, setCriticalAlertsEnabled] = useState(true);
  const [monthlyReportsEnabled, setMonthlyReportsEnabled] = useState(false);
  const [criticalAlertsSlack, setCriticalAlertsSlack] = useState(false);
  const [weeklySlackSummary, setWeeklySlackSummary] = useState(false);
  const [emailAddress, setEmailAddress] = useState("admin@company.com");
  const [slackWebhookUrl, setSlackWebhookUrl] = useState("");

  // Scheduling Settings
  const [maintenanceWindowEnabled, setMaintenanceWindowEnabled] = useState(false);
  const [maintenanceStart, setMaintenanceStart] = useState("02:00");
  const [maintenanceEnd, setMaintenanceEnd] = useState("04:00");
  const [autoOptimizeEnabled, setAutoOptimizeEnabled] = useState(true);
  const [optimizationFrequency, setOptimizationFrequency] = useState("daily");

  // Integration Settings
  const [awsIntegrationEnabled, setAwsIntegrationEnabled] = useState(true);
  const [azureIntegrationEnabled, setAzureIntegrationEnabled] = useState(false);
  const [gcpIntegrationEnabled, setGcpIntegrationEnabled] = useState(false);
  const [awsRegions, setAwsRegions] = useState("us-east-1,us-west-2");

  // Loading states
  const [loading, setLoading] = useState(false);
  const [sendingReport, setSendingReport] = useState(false);

  // Fetch notification settings on mount
  useEffect(() => {
    fetchNotificationSettings();
  }, []);

  const fetchNotificationSettings = async () => {
    try {
      const [emailRes, slackRes] = await Promise.all([
        fetch(`http://localhost:8000/notifications/email?email=${emailAddress}`),
        fetch(`http://localhost:8000/notifications/slack?email=${emailAddress}`)
      ]);

      if (emailRes.ok) {
        const emailData = await emailRes.json();
        setEmailNotificationsEnabled(emailData.email_enabled || false);
        setCriticalAlertsEnabled(emailData.critical_alerts_email !== false);
        setMonthlyReportsEnabled(emailData.monthly_reports_enabled || false);
      }

      if (slackRes.ok) {
        const slackData = await slackRes.json();
        setSlackNotificationsEnabled(slackData.slack_enabled || false);
        setCriticalAlertsSlack(slackData.critical_alerts_slack || false);
        setWeeklySlackSummary(slackData.weekly_summary_slack || false);
        setSlackWebhookUrl(slackData.slack_webhook_url || "");
      }
    } catch (error) {
      console.error("❌ Failed to fetch notification settings:", error);
    }
  };

  const handleSaveSettings = async () => {
    setLoading(true);
    try {
      const [emailRes, slackRes] = await Promise.all([
        fetch(`http://localhost:8000/notifications/email?email=${emailAddress}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email_enabled: emailNotificationsEnabled,
            critical_alerts_email: criticalAlertsEnabled,
            monthly_reports_enabled: monthlyReportsEnabled
          })
        }),
        fetch(`http://localhost:8000/notifications/slack?email=${emailAddress}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            slack_enabled: slackNotificationsEnabled,
            critical_alerts_slack: criticalAlertsSlack,
            weekly_summary_slack: weeklySlackSummary,
            slack_webhook_url: slackWebhookUrl
          })
        })
      ]);

      if (emailRes.ok && slackRes.ok) {
        toast({
          title: "Settings Saved Successfully",
          description: "Your configuration has been updated and will take effect immediately.",
        });
      } else {
        throw new Error("Failed to save settings");
      }
    } catch (error) {
      console.error("❌ Error saving settings:", error);
      toast({
        title: "Error",
        description: "Failed to save settings. Please try again.",
        variant: "destructive"
      });
    } finally {
      setLoading(false);
    }
  };

  const handleSendReportNow = async () => {
    setSendingReport(true);
    try {
      const response = await fetch("http://localhost:8000/notifications/email/send", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: emailAddress })
      });

      if (response.ok) {
        const data = await response.json();
        console.log("📧 Report sent:", data);
        toast({
          title: "Report Sent Successfully",
          description: "Monthly report has been sent to your email.",
        });
      } else {
        throw new Error("Failed to send report");
      }
    } catch (error) {
      console.error("❌ Error sending report:", error);
      toast({
        title: "Error",
        description: "Failed to send report. Make sure the backend is running.",
        variant: "destructive"
      });
    } finally {
      setSendingReport(false);
    }
  };

  const handleTestSlack = async () => {
    if (!slackWebhookUrl) {
      toast({
        title: "Error",
        description: "Please enter a Slack webhook URL first.",
        variant: "destructive"
      });
      return;
    }

    try {
      const response = await fetch("http://localhost:8000/notifications/slack/send", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          webhook_url: slackWebhookUrl,
          notification_type: "test"
        })
      });

      if (response.ok) {
        toast({
          title: "Test Message Sent",
          description: "Check your Slack channel for the test message.",
        });
      } else {
        throw new Error("Failed to send test message");
      }
    } catch (error) {
      console.error("❌ Error sending Slack test:", error);
      toast({
        title: "Error",
        description: "Failed to send test message. Check your webhook URL and backend connection.",
        variant: "destructive"
      });
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
      <motion.div variants={itemVariants}>
        <h1 className="text-3xl font-bold text-foreground">Settings</h1>
        <p className="text-muted-foreground mt-2">
          Configure your CloudOps AI agent preferences and integrations
        </p>
      </motion.div>

      <motion.div variants={itemVariants}>
        <Tabs defaultValue="notifications" className="space-y-6">
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="notifications" className="flex items-center space-x-2">
              <Bell className="h-4 w-4" />
              <span>Notifications</span>
            </TabsTrigger>
            <TabsTrigger value="scheduling" className="flex items-center space-x-2">
              <Clock className="h-4 w-4" />
              <span>Scheduling</span>
            </TabsTrigger>
            <TabsTrigger value="integrations" className="flex items-center space-x-2">
              <Cloud className="h-4 w-4" />
              <span>Integrations</span>
            </TabsTrigger>
          </TabsList>

          {/* Notifications Tab */}
          <TabsContent value="notifications" className="space-y-6">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Email Notifications */}
              <Card className="dashboard-card">
                <CardHeader>
                  <CardTitle className="flex items-center space-x-2">
                    <Mail className="h-5 w-5" />
                    <span>Email Notifications</span>
                  </CardTitle>
                  <CardDescription>
                    Configure email alerts and reports
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="flex items-center justify-between">
                    <Label htmlFor="email-enabled">Enable Email Notifications</Label>
                    <Switch
                      id="email-enabled"
                      checked={emailNotificationsEnabled}
                      onCheckedChange={setEmailNotificationsEnabled}
                    />
                  </div>
                  
                  {emailNotificationsEnabled && (
                    <div className="space-y-3">
                      <div>
                        <Label htmlFor="email-address">Email Address</Label>
                        <Input
                          id="email-address"
                          type="email"
                          value={emailAddress}
                          onChange={(e) => setEmailAddress(e.target.value)}
                          className="mt-1"
                        />
                      </div>

                      <div className="flex items-center justify-between">
                        <Label htmlFor="critical-alerts">Critical Alerts</Label>
                        <Switch
                          id="critical-alerts"
                          checked={criticalAlertsEnabled}
                          onCheckedChange={setCriticalAlertsEnabled}
                        />
                      </div>

                      <div className="flex items-center justify-between">
                        <div className="space-y-0.5 flex-1">
                          <Label htmlFor="monthly-reports">Monthly Reports</Label>
                          <p className="text-xs text-muted-foreground">
                            Comprehensive infrastructure reports
                          </p>
                        </div>
                        <div className="flex items-center gap-2">
                          <Switch
                            id="monthly-reports"
                            checked={monthlyReportsEnabled}
                            onCheckedChange={setMonthlyReportsEnabled}
                          />
                          <Button 
                            size="sm" 
                            variant="outline"
                            onClick={handleSendReportNow}
                            disabled={sendingReport}
                          >
                            {sendingReport ? "Sending..." : "Send Now"}
                          </Button>
                        </div>
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* Slack Integration */}
              <Card className="dashboard-card">
              <CardHeader>
                <CardTitle className="flex items-center space-x-2">
                  <MessageSquare className="h-5 w-5" />
                  <span>Slack Integration</span>
                </CardTitle>
                  <CardDescription>
                    Send notifications to Slack channels
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="flex items-center justify-between">
                    <Label htmlFor="slack-enabled">Enable Slack Notifications</Label>
                    <Switch
                      id="slack-enabled"
                      checked={slackNotificationsEnabled}
                      onCheckedChange={setSlackNotificationsEnabled}
                    />
                  </div>
                  
                  {slackNotificationsEnabled && (
                    <div className="space-y-4">
                      <div className="flex items-center justify-between">
                        <Label htmlFor="critical-alerts-slack">Critical Alerts</Label>
                        <Switch
                          id="critical-alerts-slack"
                          checked={criticalAlertsSlack}
                          onCheckedChange={setCriticalAlertsSlack}
                        />
                      </div>
                      
                      <div className="flex items-center justify-between">
                        <div className="space-y-0.5">
                          <Label htmlFor="weekly-slack">Weekly Summary</Label>
                          <p className="text-xs text-muted-foreground">
                            Weekly digest every Friday
                          </p>
                        </div>
                        <Switch
                          id="weekly-slack"
                          checked={weeklySlackSummary}
                          onCheckedChange={setWeeklySlackSummary}
                        />
                      </div>
                      
                      <div>
                        <div className="flex items-center justify-between mb-2">
                          <Label htmlFor="slack-webhook">Webhook URL</Label>
                          <Button 
                            size="sm" 
                            variant="outline"
                            onClick={handleTestSlack}
                            disabled={!slackWebhookUrl}
                          >
                            Test Connection
                          </Button>
                        </div>
                        <Input
                          id="slack-webhook"
                          placeholder="https://hooks.slack.com/services/..."
                          value={slackWebhookUrl}
                          onChange={(e) => setSlackWebhookUrl(e.target.value)}
                        />
                        <p className="text-xs text-muted-foreground mt-1">
                          Create a webhook in your Slack workspace settings
                        </p>
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          {/* Scheduling Tab */}
          <TabsContent value="scheduling" className="space-y-6">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Maintenance Windows */}
              <Card className="dashboard-card">
                <CardHeader>
                  <CardTitle className="flex items-center space-x-2">
                    <Clock className="h-5 w-5" />
                    <span>Maintenance Windows</span>
                  </CardTitle>
                  <CardDescription>
                    Schedule maintenance and optimization tasks
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="flex items-center justify-between">
                    <Label htmlFor="maintenance-enabled">Enable Maintenance Windows</Label>
                    <Switch
                      id="maintenance-enabled"
                      checked={maintenanceWindowEnabled}
                      onCheckedChange={setMaintenanceWindowEnabled}
                    />
                  </div>
                  
                  {maintenanceWindowEnabled && (
                    <div className="space-y-3">
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <Label htmlFor="maintenance-start">Start Time</Label>
                          <Input
                            id="maintenance-start"
                            type="time"
                            value={maintenanceStart}
                            onChange={(e) => setMaintenanceStart(e.target.value)}
                            className="mt-1"
                          />
                        </div>
                        <div>
                          <Label htmlFor="maintenance-end">End Time</Label>
                          <Input
                            id="maintenance-end"
                            type="time"
                            value={maintenanceEnd}
                            onChange={(e) => setMaintenanceEnd(e.target.value)}
                            className="mt-1"
                          />
                        </div>
                      </div>
                      <p className="text-xs text-muted-foreground">
                        Maintenance tasks will only run during this window (UTC)
                      </p>
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* Auto-Optimization */}
              <Card className="dashboard-card">
                <CardHeader>
                  <CardTitle className="flex items-center space-x-2">
                    <Settings2 className="h-5 w-5" />
                    <span>Auto-Optimization</span>
                  </CardTitle>
                  <CardDescription>
                    Configure automatic optimization settings
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="flex items-center justify-between">
                    <Label htmlFor="auto-optimize">Enable Auto-Optimization</Label>
                    <Switch
                      id="auto-optimize"
                      checked={autoOptimizeEnabled}
                      onCheckedChange={setAutoOptimizeEnabled}
                    />
                  </div>
                  
                  {autoOptimizeEnabled && (
                    <div>
                      <Label htmlFor="optimization-frequency">Optimization Frequency</Label>
                      <Select value={optimizationFrequency} onValueChange={setOptimizationFrequency}>
                        <SelectTrigger className="mt-1">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="hourly">Hourly</SelectItem>
                          <SelectItem value="daily">Daily</SelectItem>
                          <SelectItem value="weekly">Weekly</SelectItem>
                          <SelectItem value="monthly">Monthly</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          {/* Integrations Tab */}
          <TabsContent value="integrations" className="space-y-6">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Cloud Providers */}
              <Card className="dashboard-card">
                <CardHeader>
                  <CardTitle className="flex items-center space-x-2">
                    <Cloud className="h-5 w-5" />
                    <span>Cloud Providers</span>
                  </CardTitle>
                  <CardDescription>
                    Connect your cloud provider accounts
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="space-y-4">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center space-x-3">
                        <div className="h-8 w-8 bg-warning/10 rounded flex items-center justify-center">
                          <span className="text-xs font-bold text-warning">AWS</span>
                        </div>
                        <span className="font-medium">Amazon Web Services</span>
                      </div>
                      <Switch
                        checked={awsIntegrationEnabled}
                        onCheckedChange={setAwsIntegrationEnabled}
                      />
                    </div>

                    {awsIntegrationEnabled && (
                      <div className="ml-11">
                        <Label htmlFor="aws-regions">Monitored Regions</Label>
                        <Textarea
                          id="aws-regions"
                          placeholder="us-east-1, us-west-2, eu-west-1"
                          value={awsRegions}
                          onChange={(e) => setAwsRegions(e.target.value)}
                          className="mt-1 h-20"
                        />
                      </div>
                    )}

                    <div className="flex items-center justify-between">
                      <div className="flex items-center space-x-3">
                        <div className="h-8 w-8 bg-primary/10 rounded flex items-center justify-center">
                          <span className="text-xs font-bold text-primary">AZ</span>
                        </div>
                        <span className="font-medium">Microsoft Azure</span>
                      </div>
                      <Switch
                        checked={azureIntegrationEnabled}
                        onCheckedChange={setAzureIntegrationEnabled}
                      />
                    </div>

                    <div className="flex items-center justify-between">
                      <div className="flex items-center space-x-3">
                        <div className="h-8 w-8 bg-success/10 rounded flex items-center justify-center">
                          <span className="text-xs font-bold text-success">GCP</span>
                        </div>
                        <span className="font-medium">Google Cloud Platform</span>
                      </div>
                      <Switch
                        checked={gcpIntegrationEnabled}
                        onCheckedChange={setGcpIntegrationEnabled}
                      />
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Security & Compliance */}
              <Card className="dashboard-card">
                <CardHeader>
                  <CardTitle className="flex items-center space-x-2">
                    <Shield className="h-5 w-5" />
                    <span>Security & Compliance</span>
                  </CardTitle>
                  <CardDescription>
                    Configure security scanning and compliance frameworks
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <Label>SOC 2 Compliance</Label>
                      <Switch defaultChecked />
                    </div>
                    <div className="flex items-center justify-between">
                      <Label>ISO 27001</Label>
                      <Switch defaultChecked />
                    </div>
                    <div className="flex items-center justify-between">
                      <Label>GDPR Compliance</Label>
                      <Switch />
                    </div>
                    <div className="flex items-center justify-between">
                      <Label>HIPAA Compliance</Label>
                      <Switch />
                    </div>
                    <div className="flex items-center justify-between">
                      <Label>CIS Benchmarks</Label>
                      <Switch defaultChecked />
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
          </TabsContent>
        </Tabs>

        {/* Save Button */}
        <div className="flex justify-end pt-6">
          <Button 
            onClick={handleSaveSettings} 
            className="action-success"
            disabled={loading}
          >
            <Save className="h-4 w-4 mr-2" />
            {loading ? "Saving..." : "Save Settings"}
          </Button>
        </div>
      </motion.div>
    </motion.div>
  );
}
-- Create function to update timestamps
CREATE OR REPLACE FUNCTION public.handle_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create notification_settings table
CREATE TABLE public.notification_settings (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  user_email TEXT NOT NULL UNIQUE,
  email_enabled BOOLEAN NOT NULL DEFAULT false,
  slack_enabled BOOLEAN NOT NULL DEFAULT false,
  critical_alerts_email BOOLEAN NOT NULL DEFAULT true,
  monthly_reports_enabled BOOLEAN NOT NULL DEFAULT false,
  critical_alerts_slack BOOLEAN NOT NULL DEFAULT false,
  weekly_summary_slack BOOLEAN NOT NULL DEFAULT false,
  slack_webhook_url TEXT,
  last_email_sent TIMESTAMP WITH TIME ZONE,
  next_report_date TIMESTAMP WITH TIME ZONE,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- Enable RLS
ALTER TABLE public.notification_settings ENABLE ROW LEVEL SECURITY;

-- Allow public access for demo purposes
CREATE POLICY "Allow public read access to notification_settings" 
ON public.notification_settings 
FOR SELECT 
USING (true);

CREATE POLICY "Allow public insert to notification_settings" 
ON public.notification_settings 
FOR INSERT 
WITH CHECK (true);

CREATE POLICY "Allow public update to notification_settings" 
ON public.notification_settings 
FOR UPDATE 
USING (true);

CREATE POLICY "Allow public delete to notification_settings" 
ON public.notification_settings 
FOR DELETE 
USING (true);

-- Create trigger for automatic timestamp updates
CREATE TRIGGER update_notification_settings_updated_at
BEFORE UPDATE ON public.notification_settings
FOR EACH ROW
EXECUTE FUNCTION public.handle_updated_at();
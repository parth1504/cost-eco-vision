import { serve } from "https://deno.land/std@0.168.0/http/server.ts";

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

// In-memory mock data for resources
let mockResources = [
  {
    id: "i-0123456789",
    name: "web-server-1",
    type: "EC2",
    status: "Running",
    utilization: 15,
    monthlyCost: 89.50,
    region: "us-east-1",
    recommendations: ["Right-size to t3.small", "Enable detailed monitoring"],
    lastActivity: "2024-01-15T12:00:00Z"
  },
  {
    id: "prod-db",
    name: "Production Database",
    type: "RDS",
    status: "Running",
    utilization: 67,
    monthlyCost: 234.00,
    region: "us-east-1",
    recommendations: ["Remove public access", "Enable encryption"],
    lastActivity: "2024-01-15T11:30:00Z"
  },
  {
    id: "backup-bucket",
    name: "Backup Storage",
    type: "S3",
    status: "Optimized",
    utilization: 0,
    monthlyCost: 45.20,
    region: "us-east-1",
    recommendations: ["Archive old data to Glacier"],
    lastActivity: "2024-01-14T20:15:00Z"
  }
];

serve(async (req) => {
  // Handle CORS preflight requests
  if (req.method === 'OPTIONS') {
    return new Response(null, { headers: corsHeaders });
  }

  try {
    const url = new URL(req.url);
    const pathParts = url.pathname.split('/').filter(Boolean);
    
    console.log('Request:', req.method, url.pathname);

    // GET /resources/stats - Get summary statistics
    if (req.method === 'GET' && pathParts.length >= 1 && pathParts[pathParts.length - 1] === 'stats') {
      const totalResources = mockResources.length;
      const optimizedCount = mockResources.filter(r => r.status === 'Optimized').length;
      const totalUtilization = mockResources.reduce((sum, r) => sum + r.utilization, 0);
      const averageEfficiency = totalUtilization / totalResources;

      return new Response(
        JSON.stringify({
          totalResources,
          optimizedCount,
          averageEfficiency: Math.round(averageEfficiency),
          totalCost: mockResources.reduce((sum, r) => sum + r.monthlyCost, 0)
        }),
        { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      );
    }

    // POST /resources/optimize/{id} - Optimize a resource
    if (req.method === 'POST' && pathParts.includes('optimize')) {
      const resourceId = pathParts[pathParts.length - 1];
      const resourceIndex = mockResources.findIndex(r => r.id === resourceId);
      
      if (resourceIndex === -1) {
        return new Response(
          JSON.stringify({ error: 'Resource not found' }),
          { status: 404, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
        );
      }

      // Apply optimization - reduce cost by 30%
      mockResources[resourceIndex] = {
        ...mockResources[resourceIndex],
        status: 'Optimized',
        monthlyCost: Math.round(mockResources[resourceIndex].monthlyCost * 0.7 * 100) / 100,
        lastActivity: new Date().toISOString()
      };

      console.log('Optimized resource:', resourceId);

      return new Response(
        JSON.stringify(mockResources[resourceIndex]),
        { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      );
    }

    // GET /resources/{id} - Get specific resource
    if (req.method === 'GET' && pathParts.length >= 2 && pathParts[0] === 'resources') {
      const resourceId = pathParts[1];
      const resource = mockResources.find(r => r.id === resourceId);
      
      if (!resource) {
        return new Response(
          JSON.stringify({ error: 'Resource not found' }),
          { status: 404, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
        );
      }

      return new Response(
        JSON.stringify(resource),
        { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      );
    }

    // GET /resources - Get all resources (default for invoke without method)
    if (req.method === 'GET' || (req.method === 'POST' && pathParts.length === 0)) {
      return new Response(
        JSON.stringify(mockResources),
        { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      );
    }

    // POST /resources - Add new resource (with body)
    if (req.method === 'POST' && pathParts.length > 0) {
      const body = await req.json();
      const newResource = {
        id: `resource-${Date.now()}`,
        ...body,
        lastActivity: new Date().toISOString()
      };
      
      mockResources.push(newResource);
      console.log('Added new resource:', newResource.id);

      return new Response(
        JSON.stringify(newResource),
        { status: 201, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      );
    }

    // PUT /resources/{id} - Update resource
    if (req.method === 'PUT' && pathParts.length >= 2) {
      const resourceId = pathParts[1];
      const body = await req.json();
      const resourceIndex = mockResources.findIndex(r => r.id === resourceId);
      
      if (resourceIndex === -1) {
        return new Response(
          JSON.stringify({ error: 'Resource not found' }),
          { status: 404, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
        );
      }

      mockResources[resourceIndex] = {
        ...mockResources[resourceIndex],
        ...body,
        id: resourceId, // Preserve ID
        lastActivity: new Date().toISOString()
      };

      console.log('Updated resource:', resourceId);

      return new Response(
        JSON.stringify(mockResources[resourceIndex]),
        { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      );
    }

    // DELETE /resources/{id} - Delete resource
    if (req.method === 'DELETE' && pathParts.length >= 2) {
      const resourceId = pathParts[1];
      const resourceIndex = mockResources.findIndex(r => r.id === resourceId);
      
      if (resourceIndex === -1) {
        return new Response(
          JSON.stringify({ error: 'Resource not found' }),
          { status: 404, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
        );
      }

      const deletedResource = mockResources[resourceIndex];
      mockResources = mockResources.filter(r => r.id !== resourceId);
      console.log('Deleted resource:', resourceId);

      return new Response(
        JSON.stringify(deletedResource),
        { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      );
    }

    // Method not allowed
    return new Response(
      JSON.stringify({ error: 'Method not allowed' }),
      { status: 405, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );

  } catch (error) {
    console.error('Error:', error);
    return new Response(
      JSON.stringify({ error: error.message }),
      { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );
  }
});
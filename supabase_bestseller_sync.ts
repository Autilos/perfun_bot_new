import { serve } from "https://deno.land/std@0.168.0/http/server.ts"
import { createClient } from 'https://esm.sh/@supabase/supabase-client@2'

const WC_CK = Deno.env.get('PERFUN_CONSUMER_KEY')
const WC_CS = Deno.env.get('PERFUN_CONSUMER_SECRET')
const WC_URL = Deno.env.get('PERFUN_SITE_URL')
const SUPABASE_URL = Deno.env.get('FIRMY_SUPABASE_URL')
const SUPABASE_SERVICE_KEY = Deno.env.get('FIRMY_SUPABASE_KEY')

const supabase = createClient(SUPABASE_URL!, SUPABASE_SERVICE_KEY!)

serve(async (req) => {
    try {
        console.log("Starting Bestseller Sync...")

        // 1. Fetch last 100 orders from WooCommerce
        const thirtyDaysAgo = new Date();
        thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);
        const afterDate = thirtyDaysAgo.toISOString();

        const auth = btoa(`${WC_CK}:${WC_CS}`);
        const ordersUrl = `${WC_URL}/wp-json/wc/v3/orders?after=${afterDate}&per_page=100&status=processing,completed`;

        const response = await fetch(ordersUrl, {
            headers: { 'Authorization': `Basic ${auth}` }
        });

        if (!response.ok) throw new Error(`WooCommerce API error: ${response.statusText}`);
        const orders = await response.json();

        // 2. Aggregate sales
        const productCounts: Record<number, number> = {};
        orders.forEach((order: any) => {
            order.line_items.forEach((item: any) => {
                const id = item.product_id;
                if (id !== 15916) { // Skip gratis
                    productCounts[id] = (productCounts[id] || 0) + (item.quantity || 1);
                }
            });
        });

        // 3. Get Top 10 IDs
        const topIds = Object.entries(productCounts)
            .sort(([, a], [, b]) => b - a)
            .slice(0, 10)
            .map(([id]) => parseInt(id));

        console.log("Top Products identified:", topIds);

        // 4. Update Supabase
        // We update them one by one to add the tag if missing
        for (const pId of topIds) {
            const { data: records } = await supabase
                .from('perfume_knowledge_base')
                .select('id, description, name')
                .eq('wp_id', pId);

            if (records && records.length > 0) {
                const record = records[0];
                if (!record.description.includes('[BESTSELLER]')) {
                    const newDesc = record.description + "\n\n[BESTSELLER]";
                    await supabase
                        .from('perfume_knowledge_base')
                        .update({ description: newDesc })
                        .eq('id', record.id);
                    console.log(`Tagged ${record.name} as Bestseller.`);
                }
            }
        }

        return new Response(JSON.stringify({ success: true, updated_ids: topIds }), {
            headers: { "Content-Type": "application/json" },
            status: 200,
        })

    } catch (error) {
        return new Response(JSON.stringify({ error: error.message }), {
            headers: { "Content-Type": "application/json" },
            status: 500,
        })
    }
})

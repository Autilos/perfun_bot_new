import { serve } from "https://deno.land/std@0.168.0/http/server.ts"

const SELLASIST_API_KEY = Deno.env.get('SELLASIST_API_KEY')
const SELLASIST_URL = "https://perfun.sellasist.pl/api/v1"

const corsHeaders = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
}

serve(async (req) => {
    // Handle CORS
    if (req.method === 'OPTIONS') {
        return new Response('ok', { headers: corsHeaders })
    }

    try {
        const { email } = await req.json()

        if (!email) {
            return new Response(
                JSON.stringify({ error: 'Email is required' }),
                { headers: { ...corsHeaders, 'Content-Type': 'application/json' }, status: 400 }
            )
        }

        // 1. Search for orders by email
        const searchUrl = `${SELLASIST_URL}/orders?email=${encodeURIComponent(email)}&limit=1&sort=date&order=desc`
        const response = await fetch(searchUrl, {
            headers: {
                'apikey': SELLASIST_API_KEY || '',
                'Accept': 'application/json'
            }
        })

        if (response.status === 404) {
            return new Response(
                JSON.stringify({ message: "Nie znaleziono zamówień dla tego adresu email." }),
                { headers: { ...corsHeaders, 'Content-Type': 'application/json' }, status: 200 }
            )
        }

        if (!response.ok) {
            throw new Error(`Sellasist API error: ${response.statusText}`)
        }

        const orders = await response.json()
        if (!orders || orders.length === 0) {
            return new Response(
                JSON.stringify({ message: "Nie znaleziono zamówień dla tego adresu email." }),
                { headers: { ...corsHeaders, 'Content-Type': 'application/json' }, status: 200 }
            )
        }

        const order = orders[0]

        // 2. Get full details for tracking
        const detailUrl = `${SELLASIST_URL}/orders/${order.id}`
        const detailResponse = await fetch(detailUrl, {
            headers: {
                'apikey': SELLASIST_API_KEY || '',
                'Accept': 'application/json'
            }
        })

        let shipments = []
        if (detailResponse.ok) {
            const detailData = await detailResponse.json()
            shipments = detailData.shipments || []
        }

        return new Response(
            JSON.stringify({
                id: order.id,
                status: order.status?.name || 'Brak statusu',
                date: order.date,
                total: order.total,
                currency: order.payment?.currency || 'PLN',
                shipments: shipments.map((s: any) => ({
                    number: s.tracking_number,
                    courier: s.courier_name || s.service || 'Kurier'
                }))
            }),
            { headers: { ...corsHeaders, 'Content-Type': 'application/json' }, status: 200 }
        )

    } catch (error) {
        return new Response(
            JSON.stringify({ error: error.message }),
            { headers: { ...corsHeaders, 'Content-Type': 'application/json' }, status: 500 }
        )
    }
})

/**
 * seed-products.js — Seed the full NegotiateIQ product catalogue into Firestore.
 *
 * Run locally:
 *   FIREBASE_PROJECT_ID=negotiateiq-510510 node firestore/seed-products.js
 *
 * Or with a service account key:
 *   GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json \
 *   FIREBASE_PROJECT_ID=negotiateiq-510510 \
 *   node firestore/seed-products.js
 *
 * The two catalogues are also available as CSVs (data/catalogue_electronics.csv
 * and data/catalogue_furniture.csv) for import via the merchant Config tab.
 */

const { initializeApp, cert, getApps } = require("firebase-admin/app");
const { getFirestore }                  = require("firebase-admin/firestore");

if (!getApps().length) {
  initializeApp({ projectId: process.env.FIREBASE_PROJECT_ID });
}
const db = getFirestore();

// ---------------------------------------------------------------------------
// Catalogue A — Consumer Electronics (SKU-E01 … SKU-E10)
// ---------------------------------------------------------------------------
const electronics = [
  {
    sku: "SKU-E01",
    name: "Google Pixel 9 Pro",
    list_price: 899.00,
    price_floor: 719.00,
    bulk_tiers: [{ min_qty: 10, discount_pct: 8 }, { min_qty: 50, discount_pct: 15 }],
    delivery_options: ["standard_5d", "express_2d"],
    vouchers_eligible: true,
    image_url: "https://picsum.photos/seed/pixel9pro/400/280",
  },
  {
    sku: "SKU-E02",
    name: "Google Pixel 9a",
    list_price: 499.00,
    price_floor: 399.00,
    bulk_tiers: [{ min_qty: 10, discount_pct: 8 }, { min_qty: 50, discount_pct: 15 }],
    delivery_options: ["standard_5d", "express_2d"],
    vouchers_eligible: true,
    image_url: "https://picsum.photos/seed/pixel9a/400/280",
  },
  {
    sku: "SKU-E03",
    name: "Google Pixel Watch 3 (45mm)",
    list_price: 349.99,
    price_floor: 279.99,
    bulk_tiers: [{ min_qty: 5, discount_pct: 8 }, { min_qty: 20, discount_pct: 13 }],
    delivery_options: ["standard_5d", "express_2d"],
    vouchers_eligible: true,
    image_url: "https://picsum.photos/seed/pixelwatch3/400/280",
  },
  {
    sku: "SKU-E04",
    name: "Google Pixel Buds Pro 2",
    list_price: 229.99,
    price_floor: 179.99,
    bulk_tiers: [{ min_qty: 10, discount_pct: 8 }, { min_qty: 50, discount_pct: 14 }],
    delivery_options: ["standard_5d", "express_2d"],
    vouchers_eligible: true,
    image_url: "https://picsum.photos/seed/pixelbuds/400/280",
  },
  {
    sku: "SKU-E05",
    name: 'HP EliteBook 840 G11 14" Laptop',
    list_price: 1299.00,
    price_floor: 1039.00,
    bulk_tiers: [{ min_qty: 5, discount_pct: 6 }, { min_qty: 20, discount_pct: 12 }],
    delivery_options: ["standard_5d"],
    vouchers_eligible: false,
    image_url: "https://picsum.photos/seed/elitebook/400/280",
  },
  {
    sku: "SKU-E06",
    name: "HP OfficeJet Pro 9135e All-in-One Printer",
    list_price: 399.99,
    price_floor: 309.99,
    bulk_tiers: [{ min_qty: 5, discount_pct: 8 }, { min_qty: 25, discount_pct: 15 }],
    delivery_options: ["standard_5d"],
    vouchers_eligible: true,
    image_url: "https://picsum.photos/seed/officejet/400/280",
  },
  {
    sku: "SKU-E07",
    name: 'Samsung Galaxy Tab S10+ 12.4"',
    list_price: 749.99,
    price_floor: 599.99,
    bulk_tiers: [{ min_qty: 5, discount_pct: 7 }, { min_qty: 20, discount_pct: 13 }],
    delivery_options: ["standard_5d", "express_2d"],
    vouchers_eligible: true,
    image_url: "https://picsum.photos/seed/tabs10/400/280",
  },
  {
    sku: "SKU-E08",
    name: "Sony WH-1000XM6 Wireless Headphones",
    list_price: 349.99,
    price_floor: 279.99,
    bulk_tiers: [{ min_qty: 10, discount_pct: 8 }, { min_qty: 50, discount_pct: 15 }],
    delivery_options: ["standard_5d", "express_2d"],
    vouchers_eligible: true,
    image_url: "https://picsum.photos/seed/sonyxm6/400/280",
  },
  {
    sku: "SKU-E09",
    name: "Logitech MX Keys S Wireless Keyboard",
    list_price: 119.99,
    price_floor: 94.99,
    bulk_tiers: [{ min_qty: 10, discount_pct: 8 }, { min_qty: 50, discount_pct: 15 }],
    delivery_options: ["standard_5d", "express_2d"],
    vouchers_eligible: false,
    image_url: "https://picsum.photos/seed/mxkeys/400/280",
  },
  {
    sku: "SKU-E10",
    name: 'LG 32" 4K IPS Monitor (32UP83A)',
    list_price: 599.99,
    price_floor: 479.99,
    bulk_tiers: [{ min_qty: 3, discount_pct: 5 }, { min_qty: 10, discount_pct: 12 }],
    delivery_options: ["standard_5d"],
    vouchers_eligible: true,
    image_url: "https://picsum.photos/seed/lgmonitor32/400/280",
  },
];

// ---------------------------------------------------------------------------
// Catalogue B — Home & Furniture (SKU-H01 … SKU-H10)
// ---------------------------------------------------------------------------
const furniture = [
  {
    sku: "SKU-H01",
    name: "Ergohuman Elite V2 Ergonomic Office Chair",
    list_price: 699.00,
    price_floor: 559.00,
    bulk_tiers: [{ min_qty: 5, discount_pct: 8 }, { min_qty: 20, discount_pct: 15 }],
    delivery_options: ["standard_5d"],
    vouchers_eligible: true,
    image_url: "https://picsum.photos/seed/officchair/400/280",
  },
  {
    sku: "SKU-H02",
    name: "Flexispot E7 Pro Electric Standing Desk (140×70 cm)",
    list_price: 549.99,
    price_floor: 439.99,
    bulk_tiers: [{ min_qty: 5, discount_pct: 8 }, { min_qty: 10, discount_pct: 13 }],
    delivery_options: ["standard_5d"],
    vouchers_eligible: true,
    image_url: "https://picsum.photos/seed/standingdesk/400/280",
  },
  {
    sku: "SKU-H03",
    name: "IKEA KALLAX 4×2 Shelf Unit (White)",
    list_price: 219.99,
    price_floor: 169.99,
    bulk_tiers: [{ min_qty: 5, discount_pct: 8 }, { min_qty: 20, discount_pct: 15 }],
    delivery_options: ["standard_5d"],
    vouchers_eligible: false,
    image_url: "https://picsum.photos/seed/kallax/400/280",
  },
  {
    sku: "SKU-H04",
    name: "Casper Wave Hybrid Mattress (Queen)",
    list_price: 1999.00,
    price_floor: 1599.00,
    bulk_tiers: [{ min_qty: 2, discount_pct: 5 }, { min_qty: 5, discount_pct: 10 }],
    delivery_options: ["standard_5d"],
    vouchers_eligible: true,
    image_url: "https://picsum.photos/seed/mattress/400/280",
  },
  {
    sku: "SKU-H05",
    name: "Philips Hue White & Color Starter Kit (4 Bulbs + Bridge)",
    list_price: 199.99,
    price_floor: 154.99,
    bulk_tiers: [{ min_qty: 10, discount_pct: 8 }, { min_qty: 50, discount_pct: 15 }],
    delivery_options: ["standard_5d", "express_2d"],
    vouchers_eligible: true,
    image_url: "https://picsum.photos/seed/philipshue/400/280",
  },
  {
    sku: "SKU-H06",
    name: "Dyson V15 Detect Cordless Vacuum Cleaner",
    list_price: 749.99,
    price_floor: 599.99,
    bulk_tiers: [{ min_qty: 3, discount_pct: 7 }, { min_qty: 10, discount_pct: 13 }],
    delivery_options: ["standard_5d", "express_2d"],
    vouchers_eligible: true,
    image_url: "https://picsum.photos/seed/dysonv15/400/280",
  },
  {
    sku: "SKU-H07",
    name: "Nespresso Vertuo Next Coffee Machine",
    list_price: 229.99,
    price_floor: 179.99,
    bulk_tiers: [{ min_qty: 5, discount_pct: 8 }, { min_qty: 20, discount_pct: 15 }],
    delivery_options: ["standard_5d", "express_2d"],
    vouchers_eligible: true,
    image_url: "https://picsum.photos/seed/nespresso/400/280",
  },
  {
    sku: "SKU-H08",
    name: "Kindle Scribe 64GB Premium Pen Bundle",
    list_price: 339.99,
    price_floor: 269.99,
    bulk_tiers: [{ min_qty: 5, discount_pct: 8 }, { min_qty: 20, discount_pct: 13 }],
    delivery_options: ["standard_5d", "express_2d"],
    vouchers_eligible: true,
    image_url: "https://picsum.photos/seed/kindlescribe/400/280",
  },
  {
    sku: "SKU-H09",
    name: "Ring Video Doorbell Pro 2 + Chime Pro",
    list_price: 279.99,
    price_floor: 219.99,
    bulk_tiers: [{ min_qty: 5, discount_pct: 8 }, { min_qty: 25, discount_pct: 15 }],
    delivery_options: ["standard_5d", "express_2d"],
    vouchers_eligible: true,
    image_url: "https://picsum.photos/seed/ringdoorbell/400/280",
  },
  {
    sku: "SKU-H10",
    name: "LIFX A19 Smart LED Bulb (10-pack)",
    list_price: 149.99,
    price_floor: 114.99,
    bulk_tiers: [{ min_qty: 10, discount_pct: 8 }, { min_qty: 50, discount_pct: 14 }],
    delivery_options: ["standard_5d", "express_2d"],
    vouchers_eligible: false,
    image_url: "https://picsum.photos/seed/lifxbulb/400/280",
  },
];

// ---------------------------------------------------------------------------
// Seed
// ---------------------------------------------------------------------------
async function seed() {
  const all = [...electronics, ...furniture];
  for (const p of all) {
    await db.collection("products").doc(p.sku).set(p);
    console.log(`Seeded: ${p.sku} — ${p.name}`);
  }
  console.log(`\nDone. ${all.length} products written to Firestore.`);
}

seed().catch(console.error);

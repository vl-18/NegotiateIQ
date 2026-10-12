/**
 * App.jsx — Buyer Portal root layout.
 * Two tabs: Products and Negotiate.
 * Products are fetched from the backend so merchant changes (add/delete/edit) are always live.
 */

import { useState, useEffect } from "react";
import { fetchProducts, normalizeProduct } from "./api.js";
import Sidebar           from "./components/Sidebar.jsx";
import ProductsScreen    from "./components/ProductsScreen.jsx";
import NegotiationScreen from "./components/NegotiationScreen.jsx";
import ThemeToggle       from "./components/ThemeToggle.jsx";


export default function App() {
  const [products,        setProducts]        = useState([]);
  const [productsLoading, setProductsLoading] = useState(true);
  const [activeTab,       setActiveTab]       = useState("products");
  const [selectedProduct, setSelectedProduct] = useState(null);
  const [session,         setSession]         = useState(null);

  useEffect(() => {
    fetchProducts()
      .then((data) => setProducts((data.products ?? []).map(normalizeProduct)))
      .catch(() => {})   // show empty grid on error rather than crashing
      .finally(() => setProductsLoading(false));
  }, []);

  function handleProductSelect(product) {
    setSelectedProduct(product);
    setActiveTab("negotiate");
  }

  const screens = {
    products: (
      <ProductsScreen
        products={products}
        loading={productsLoading}
        selectedSku={selectedProduct?.sku}
        onSelect={handleProductSelect}
      />
    ),
    negotiate: (
      <NegotiationScreen
        product={selectedProduct}
        session={session}
        onSessionStarted={(data) => setSession(data)}
        onReset={() => setSession(null)}
        onGoToProducts={() => setActiveTab("products")}
      />
    ),
  };

  return (
    <div className="flex h-screen overflow-hidden bg-[var(--bg)] text-[var(--text-1)]">
      <ThemeToggle />
      <Sidebar
        activeTab={activeTab}
        onTabChange={setActiveTab}
        hasActiveSession={!!session}
      />
      <main className="flex-1 overflow-y-auto">
        {screens[activeTab]}
      </main>
    </div>
  );
}

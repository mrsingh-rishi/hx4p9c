import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Accuracy } from "./Accuracy";
import { Desk } from "./Desk";

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Desk />} />
        <Route path="/accuracy" element={<Accuracy />} />
      </Routes>
    </BrowserRouter>
  );
}

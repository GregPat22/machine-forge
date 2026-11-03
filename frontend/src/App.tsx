import { Route, Routes } from "react-router-dom";
import Home from "./pages/Home";
import ProjectPage from "./pages/ProjectPage";
import Suppliers from "./pages/Suppliers";

export default function App() {
  return <Routes><Route path="/" element={<Home />} /><Route path="/projects/:id" element={<ProjectPage />} /><Route path="/suppliers" element={<Suppliers />} /></Routes>;
}

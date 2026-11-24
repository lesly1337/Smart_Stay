import Menu from "./Front/Menu.jsx";

export default function App() {
  return <Menu onBack={() => console.log("Назад")} />;
}

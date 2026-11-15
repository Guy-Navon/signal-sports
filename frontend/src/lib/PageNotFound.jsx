import { Link } from "react-router-dom";
import AuthScene from "@/pages/AuthScene";

export default function PageNotFound() {
  return (
    <AuthScene title="הדף הזה לא נמצא">
      <p className="sg-auth-footer"><Link to="/">חזרה לפיד</Link></p>
    </AuthScene>
  );
}

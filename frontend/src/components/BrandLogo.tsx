import lightLogo from "../assets/TechniView_Logo_Light.svg";
import darkLogo from "../assets/TechniView_Logo_Dark.svg";

export default function BrandLogo() {
    return (
        <>
            <img className="brand-logo-light" src={lightLogo} alt="TechniView" />
            <img className="brand-logo-dark" src={darkLogo} alt="TechniView" />
        </>
    );
}

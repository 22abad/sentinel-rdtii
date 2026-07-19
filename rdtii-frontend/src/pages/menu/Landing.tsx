import Footer from "@/components/Footer/Footer";
import { Hero } from "@/components/Hero/Hero";
import { Label } from "@/components/Label/Label";
import { Description } from "@/components/Description/Description";
import { Placeholder } from "@/components/Placeholder";
import { BrandSpecimen } from "@/components/BrandSpecimen/BrandSpecimen";


export function LandingPage() {
  return (
    <main>
      <div className="relative">
        <Hero />
        <Label />
        <BrandSpecimen />
        <Placeholder />
        <Description />
        <Footer />
      </div>
    </main>
  );
}

// Device presets for the "Camera / phone" picker.
// Add your own: { label, make, model, software, style }   style: "apple" | "android" | "camera"
// - apple:   writes com.apple.quicktime.make/model/software (what iPhones write)
// - android: writes com.android.manufacturer/model/version (what Android phones write)
// - camera:  writes plain make/model tags only
// `software` is the OS/firmware version string; edit it after picking if you like.
window.CHEEZY_DEVICES = [
  { group: "iPhone 17", items: [
    { label: "iPhone 17 Pro Max", make: "Apple", model: "iPhone 17 Pro Max", software: "26.1", style: "apple" },
    { label: "iPhone 17 Pro",     make: "Apple", model: "iPhone 17 Pro",     software: "26.1", style: "apple" },
    { label: "iPhone Air",        make: "Apple", model: "iPhone Air",        software: "26.1", style: "apple" },
    { label: "iPhone 17",         make: "Apple", model: "iPhone 17",         software: "26.1", style: "apple" },
  ]},
  { group: "iPhone 16", items: [
    { label: "iPhone 16 Pro Max", make: "Apple", model: "iPhone 16 Pro Max", software: "26.1", style: "apple" },
    { label: "iPhone 16 Pro",     make: "Apple", model: "iPhone 16 Pro",     software: "26.1", style: "apple" },
    { label: "iPhone 16 Plus",    make: "Apple", model: "iPhone 16 Plus",    software: "26.1", style: "apple" },
    { label: "iPhone 16",         make: "Apple", model: "iPhone 16",         software: "26.1", style: "apple" },
    { label: "iPhone 16e",        make: "Apple", model: "iPhone 16e",        software: "26.1", style: "apple" },
  ]},
  { group: "iPhone 15", items: [
    { label: "iPhone 15 Pro Max", make: "Apple", model: "iPhone 15 Pro Max", software: "26.1", style: "apple" },
    { label: "iPhone 15 Pro",     make: "Apple", model: "iPhone 15 Pro",     software: "26.1", style: "apple" },
    { label: "iPhone 15 Plus",    make: "Apple", model: "iPhone 15 Plus",    software: "26.1", style: "apple" },
    { label: "iPhone 15",         make: "Apple", model: "iPhone 15",         software: "26.1", style: "apple" },
  ]},
  { group: "Samsung Galaxy", items: [
    { label: "Galaxy S25 Ultra", make: "samsung", model: "SM-S938B", software: "15", style: "android" },
    { label: "Galaxy S25+",      make: "samsung", model: "SM-S936B", software: "15", style: "android" },
    { label: "Galaxy S25",       make: "samsung", model: "SM-S931B", software: "15", style: "android" },
    { label: "Galaxy S24 Ultra", make: "samsung", model: "SM-S928B", software: "15", style: "android" },
    { label: "Galaxy S24",       make: "samsung", model: "SM-S921B", software: "15", style: "android" },
  ]},
  { group: "Google Pixel", items: [
    { label: "Pixel 10 Pro XL", make: "Google", model: "Pixel 10 Pro XL", software: "16", style: "android" },
    { label: "Pixel 10 Pro",    make: "Google", model: "Pixel 10 Pro",    software: "16", style: "android" },
    { label: "Pixel 10",        make: "Google", model: "Pixel 10",        software: "16", style: "android" },
    { label: "Pixel 9 Pro XL",  make: "Google", model: "Pixel 9 Pro XL",  software: "16", style: "android" },
    { label: "Pixel 9 Pro",     make: "Google", model: "Pixel 9 Pro",     software: "16", style: "android" },
    { label: "Pixel 9",         make: "Google", model: "Pixel 9",         software: "16", style: "android" },
  ]},
  { group: "Cameras", items: [
    { label: "Sony α7 IV",        make: "Sony",   model: "ILCE-7M4",       software: "", style: "camera" },
    { label: "Canon EOS R5",      make: "Canon",  model: "Canon EOS R5",   software: "", style: "camera" },
    { label: "GoPro HERO13 Black", make: "GoPro", model: "HERO13 Black",   software: "", style: "camera" },
  ]},
];

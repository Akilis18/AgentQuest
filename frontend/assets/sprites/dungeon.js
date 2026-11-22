// Original 8 × 8 sprites. A dot is transparent.
export const sprites = {
  player: ["..gggg..", ".gggggg.", ".gssssg.", ".gsdssg.", "..ssss..", ".gggggw.", ".gggggw.", "..d..d.."],
  guard: ["..aaaa..", ".aaaaaa.", ".awwawa.", "..ssss..", ".arrrra.", "warrraa.", "w.rrrr..", "..a..a.."],
  distracted: ["..aaaa..", ".aaaaaa.", ".awawaa.", "..ssss..", ".ammmma.", "..mmmm..", "..mmmm..", "..a..a.."],
  locked: [".oooooo.", ".obbbbo.", ".obobbo.", ".obobbo.", ".wowogo.", ".obobbo.", ".obobbo.", ".oooooo."],
  unlocked: [".oooooo.", ".oddddo.", ".oddddo.", ".oddddo.", ".oddddo.", ".oddddo.", ".oddddo.", ".o....o."],
  armed: ["........", "........", "..w..w..", ".w.ww.w.", ".a.aa.a.", ".rrrrrr.", "..aaaa..", "........"],
  disarmed: ["........", "........", "........", "........", "..m..m..", ".ammmma.", "..aaaa..", "........"],
  key: ["........", "...gg...", "..gwwg..", "..gddg..", "...ggg..", "...g....", "...gg...", "........"],
  toolkit: ["........", "........", "..aaaa..", ".awwwwa.", ".ammmma.", ".amgmma.", ".aaaaaa.", "........"],
  decoy: ["........", "..rrrr..", ".rwwwwr.", ".rwrwwr.", "..rrrr..", "...bb...", "..bbbb..", "........"],
  treasure: ["........", "..gggg..", ".gbbbbg.", ".gggggg.", ".bbybbb.", ".bbbbbb.", ".gggggg.", "........"],
  plaque: ["........", ".aaaaaa.", ".agggga.", ".agybga.", ".agggga.", ".aaaaaa.", "........", "........"],
  exit: ["..mmmm..", ".mmwwmm.", "mmddddmm", "mddmdddm", "mddmmddm", "mddmdddm", "mddddddm", "mmmmmmmm"],
};

export const palette = {
  a: "#525e64", b: "#985932", d: "#151e19", g: "#f2c46d",
  m: "#60be94", o: "#714d35", r: "#bb5e56", s: "#ebb692",
  w: "#d7e2d6", y: "#fff0a1",
};

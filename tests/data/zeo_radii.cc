/*
 * The radius table from Zeo++ 0.3's networkinfo.cc, excerpted
 * verbatim so that tests/test_porosity.py can check
 * xtal.analysis.porosity.ZEO_RADII in a checkout that has no Zeo++
 * source.  Zeo++'s licence, which this excerpt carries with it:
 *
 * Zeo++ Copyright (c) 2011, The Regents of the University
 * of California, through Lawrence Berkeley National Laboratory (subject
 * to receipt of any required approvals from the U.S. Dept. of Energy).
 * All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are
 * met:
 *
 * (1) Redistributions of source code must retain the above copyright
 * notice, this list of conditions and the following disclaimer.
 *
 * (2) Redistributions in binary form must reproduce the above copyright
 * notice, this list of conditions and the following disclaimer in the
 * documentation and/or other materials provided with the distribution.
 *
 * (3) Neither the name of the University of California, Lawrence
 * Berkeley National Laboratory, U.S. Dept. of Energy nor the names of
 * its contributors may be used to endorse or promote products derived
 * from this software without specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
 * "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
 * LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
 * A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
 * OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
 * SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
 * LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
 * DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
 * THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
 * (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
 * OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 *
 * You are under no obligation whatsoever to provide any bug fixes,
 * patches, or upgrades to the features, functionality or performance of
 * the source code ("Enhancements") to anyone; however, if you choose to
 * make your Enhancements available either publicly, or directly to
 * Lawrence Berkeley National Laboratory, without imposing a separate
 * written license agreement for such Enhancements, then you hereby grant
 * the following license: a  non-exclusive, royalty-free perpetual
 * license to install, use, modify, prepare derivative works, incorporate
 * into other computer software, distribute, and sublicense such
 * enhancements or derivative works thereof, in binary and source code
 * form.
 */

void initializeRadTable(){
//radTable.insert(pair <string,double> ("Symbol",  vdW_Radius));
radTable.insert(pair <string,double> ("H",  1.09));
radTable.insert(pair <string,double> ("D",  1.09));
radTable.insert(pair <string,double> ("He",  1.4));
radTable.insert(pair <string,double> ("Li",  1.82));
radTable.insert(pair <string,double> ("Be",  2));
radTable.insert(pair <string,double> ("B",  2));
radTable.insert(pair <string,double> ("C",  1.7));
radTable.insert(pair <string,double> ("N",  1.55));
radTable.insert(pair <string,double> ("O",  1.52));
radTable.insert(pair <string,double> ("F",  1.47));
radTable.insert(pair <string,double> ("Ne",  1.54));
radTable.insert(pair <string,double> ("Na",  2.27));
radTable.insert(pair <string,double> ("Mg",  1.73));
radTable.insert(pair <string,double> ("Al",  2));
radTable.insert(pair <string,double> ("Si",  2.1));
radTable.insert(pair <string,double> ("P",  1.8));
radTable.insert(pair <string,double> ("S",  1.8));
radTable.insert(pair <string,double> ("Cl",  1.75));
radTable.insert(pair <string,double> ("Ar",  1.88));
radTable.insert(pair <string,double> ("K",  2.75));
radTable.insert(pair <string,double> ("Ca",  2));
radTable.insert(pair <string,double> ("Sc",  2));
radTable.insert(pair <string,double> ("Ti",  2));
radTable.insert(pair <string,double> ("V",  2));
radTable.insert(pair <string,double> ("Cr",  2));
radTable.insert(pair <string,double> ("Mn",  2));
radTable.insert(pair <string,double> ("Fe",  2));
radTable.insert(pair <string,double> ("Co",  2));
radTable.insert(pair <string,double> ("Ni",  1.63));
radTable.insert(pair <string,double> ("Cu",  1.4));
radTable.insert(pair <string,double> ("Zn",  1.39));
radTable.insert(pair <string,double> ("Ga",  1.87));
radTable.insert(pair <string,double> ("Ge",  2));
radTable.insert(pair <string,double> ("As",  1.85));
radTable.insert(pair <string,double> ("Se",  1.9));
radTable.insert(pair <string,double> ("Br",  1.85));
radTable.insert(pair <string,double> ("Kr",  2.02));
radTable.insert(pair <string,double> ("Rb",  2));
radTable.insert(pair <string,double> ("Sr",  2));
radTable.insert(pair <string,double> ("Y",  2));
radTable.insert(pair <string,double> ("Zr",  2));
radTable.insert(pair <string,double> ("Nb",  2));
radTable.insert(pair <string,double> ("Mo",  2));
radTable.insert(pair <string,double> ("Tc",  2));
radTable.insert(pair <string,double> ("Ru",  2));
radTable.insert(pair <string,double> ("Rh",  2));
radTable.insert(pair <string,double> ("Pd",  1.63));
radTable.insert(pair <string,double> ("Ag",  1.72));
radTable.insert(pair <string,double> ("Cd",  1.58));
radTable.insert(pair <string,double> ("In",  1.93));
radTable.insert(pair <string,double> ("Sn",  2.17));
radTable.insert(pair <string,double> ("Sb",  2));
radTable.insert(pair <string,double> ("Te",  2.06));
radTable.insert(pair <string,double> ("I",  1.98));
radTable.insert(pair <string,double> ("Xe",  2.16));
radTable.insert(pair <string,double> ("Cs",  2));
radTable.insert(pair <string,double> ("Ba",  2));
radTable.insert(pair <string,double> ("La",  2));
radTable.insert(pair <string,double> ("Ce",  2));
radTable.insert(pair <string,double> ("Pr",  2));
radTable.insert(pair <string,double> ("Nd",  2));
radTable.insert(pair <string,double> ("Pm",  2));
radTable.insert(pair <string,double> ("Sm",  2));
radTable.insert(pair <string,double> ("Eu",  2));
radTable.insert(pair <string,double> ("Gd",  2));
radTable.insert(pair <string,double> ("Tb",  2));
radTable.insert(pair <string,double> ("Dy",  2));
radTable.insert(pair <string,double> ("Ho",  2));
radTable.insert(pair <string,double> ("Er",  2));
radTable.insert(pair <string,double> ("Tm",  2));
radTable.insert(pair <string,double> ("Yb",  2));
radTable.insert(pair <string,double> ("Lu",  2));
radTable.insert(pair <string,double> ("Hf",  2));
radTable.insert(pair <string,double> ("Ta",  2));
radTable.insert(pair <string,double> ("W",  2));
radTable.insert(pair <string,double> ("Re",  2));
radTable.insert(pair <string,double> ("Os",  2));
radTable.insert(pair <string,double> ("Ir",  2));
radTable.insert(pair <string,double> ("Pt",  1.72));
radTable.insert(pair <string,double> ("Au",  1.66));
radTable.insert(pair <string,double> ("Hg",  1.55));
radTable.insert(pair <string,double> ("Tl",  1.96));
radTable.insert(pair <string,double> ("Pb",  2.02));
radTable.insert(pair <string,double> ("Bi",  2));
radTable.insert(pair <string,double> ("Po",  2));
radTable.insert(pair <string,double> ("At",  2));
radTable.insert(pair <string,double> ("Rn",  2));
radTable.insert(pair <string,double> ("Fr",  2));
radTable.insert(pair <string,double> ("Ra",  2));
radTable.insert(pair <string,double> ("Ac",  2));
radTable.insert(pair <string,double> ("Th",  2));
radTable.insert(pair <string,double> ("Pa",  2));
radTable.insert(pair <string,double> ("U",  1.86));
radTable.insert(pair <string,double> ("Np",  2));
radTable.insert(pair <string,double> ("Pu",  2));
radTable.insert(pair <string,double> ("Am",  2));
radTable.insert(pair <string,double> ("Cm",  2));
radTable.insert(pair <string,double> ("Bk",  2));
radTable.insert(pair <string,double> ("Cf",  2));
radTable.insert(pair <string,double> ("Es",  2));
radTable.insert(pair <string,double> ("Fm",  2));
radTable.insert(pair <string,double> ("Md",  2));
radTable.insert(pair <string,double> ("No",  2));
radTable.insert(pair <string,double> ("Lr",  2));
radTable.insert(pair <string,double> ("Rf",  2));
radTable.insert(pair <string,double> ("Db",  2));
radTable.insert(pair <string,double> ("Sg",  2));
radTable.insert(pair <string,double> ("Bh",  2));
radTable.insert(pair <string,double> ("Hs",  2));
radTable.insert(pair <string,double> ("Mt",  2));
radTable.insert(pair <string,double> ("Ds",  2));
}

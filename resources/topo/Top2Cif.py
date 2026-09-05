from subprocess import run
import gemmi
from pyxtal import pyxtal
from gemmi import cif
import numpy as np

# Calculate efficiencies for 3D topologies
def threedim():
	# Set the scale of the unit cell
	scale = 8.0
	num = 8
	# Keep track of index
	count = 0

	# Read in the RCSR
	f = open("RCSRnets-2019-06-01.cgd", 'r')
	lines = f.readlines()
	f.close()

	# Output spreadsheet
	h = open("topology2.csv",'w')

	check = True
	#check = False
	for i,line in enumerate(lines):
		# To start halfway through the list
		#if not check and len(line.split()) == 2 and line.split()[0] == "NAME" and line.split()[1] == "dia-f":
		#	check = True

		if check and len(line.split()) == 2 and line.split()[0] == "NAME" and len(lines[i+2].split()) == 7:# and line.split()[1] == "pcu":

			# Parse the RCSR topology
			j = 0
			name = line.split()[1]
			cell = []
			atoms = []
			group = ""
			edge = []
			node = []
			while lines[i+j].split()[0] != "END":
				if lines[i+j].split()[0] == "CELL":
					cell = lines[i+j].split()[1:]
				elif lines[i+j].split()[0] == "NODE":
					atoms.append(lines[i+j].split()[3:])
					node.append(lines[i+j].split()[2])
				elif lines[i+j].split()[0] == "GROUP":
					group = lines[i+j].split()[1]
				elif lines[i+j].split()[0] == "EDGE":
					edge.append(lines[i+j].split()[1:])
				j += 1

			# Determine cell parameters
			a = str(scale * float(cell[0]))
			b = str(scale * float(cell[1]))
			c = str(scale * float(cell[2]))
			al = cell[3]
			be = cell[4]
			ga = cell[5]

			# Find the spacegroup
			sg = gemmi.find_spacegroup_by_name(group)
			group = str(sg.number)

			# Write a dummy .cif file
			g = open('Tops2/%s.cif' % name,'w')
			g.write('data_pcu\n')
			g.write('_cell_length_a ' + a + '\n')
			g.write('_cell_length_b ' + b + '\n')
			g.write('_cell_length_c ' + c + '\n')
			g.write('_cell_angle_alpha ' + al + '\n')
			g.write('_cell_angle_beta ' + be + '\n')
			g.write('_cell_angle_gamma ' + ga + '\n')
			g.write('_space_group_IT_number \'' + str(sg.number) + '\'\n')
			g.write('_symmetry_space_group_name_H-M_alt \'' + sg.hm + '\'\n')
			g.write('_space_group_name_Hall \'' + sg.hall + '\'\n')
			g.write('loop_\n')
			g.write(' _atom_site_label\n')
			g.write(' _atom_site_type_symbol\n')
			g.write(' _atom_site_fract_x\n')
			g.write(' _atom_site_fract_y\n')
			g.write(' _atom_site_fract_z\n')
			g.write(' _atom_site_occupancy\n')

			# Insert H at the nodes and He along the edges
			for k in range(len(atoms)):
				g.write('  H'+str(k)+' H ' + atoms[k][0] + ' ' + atoms[k][1] + ' ' + atoms[k][2] + ' 0.1\n')
			for k in range(len(edge)):
				for l in range(num):
					n = float(l + 1)
					m = float(num - n)
					aa = str((((float(edge[k][0]) * m) + (float(edge[k][3])) * n)) / float(num))
					bb = str((((float(edge[k][1]) * m) + (float(edge[k][4])) * n)) / float(num))
					cc = str((((float(edge[k][2]) * m) + (float(edge[k][5])) * n)) / float(num))
					g.write('  He'+str(k+len(atoms)+l)+'  He ' + aa + ' ' + bb + ' ' + cc + ' 0.1\n')

			g.close()

			# Increment index
			count += 1

			# Calculate the number of edges per unit cell
			my_crystal = pyxtal()
			my_crystal.from_seed(seed='Tops2/%s.cif' % name, style='pyxtal')
			sitecount = my_crystal.get_site_labels()['H']
			deg = []

			# Error handling
			if len(sitecount) == len(node):
				for k in range(len(node)):
					sym = float(sitecount[k].translate({ord(kk): None for kk in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'}))
					deg.append(sym*float(node[k])/2)
			elif len(sitecount) != len(node):
				print('CHECK: ',name)

				noder = []
				for k in range(len((my_crystal.get_site_labels()['He']))):
					noder.append(int(my_crystal.get_site_labels()['He'][k].translate({ord(kk): None for kk in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'})))
				deg2 = sum(noder)/(num-1)
				if sum(deg) != deg2:
					print('Wrong',deg,deg2)
					if not deg2.is_integer():
						print('EXTRA CHECK: ',name)
						continue
					deg = [deg2]

			# Calculate unit cell volume
			a = float(a)
			b = float(b)
			c = float(c)
			al = float(al)*np.pi/180
			be = float(be)*np.pi/180
			ga = float(ga)*np.pi/180
			vol = a * b * c * np.sqrt(1-np.cos(al)**2-np.cos(be)**2-np.cos(ga)**2+2*np.cos(al)*np.cos(be)*np.cos(ga))

			# Calculate the largest cavity diameter using Zeo++
			cmd = "/Users/julesoppenheim/Downloads/zeo++-0.3/network -ha -res Tops2/%s.cif" % name
			data = run(cmd, capture_output=True, shell=True)
			zf = open('Tops2/' + name + ".res")
			zlines = zf.readlines()
			zf.close()
			lcda = float([x for x in zlines[0].split(' ') if x][1])

			# Output results to terminal and spreadsheet
			print(name + '  \t' + str(vol / (sum(deg) * float(lcda**2))))
			h.write(name+','+str(lcda)+','+str(sum(deg))+','+str(vol)+','+str(vol / (sum(deg) * scale * float(lcda**2)))+'\n')

		# Break for testing
		#if count == 1:
		#	break
	h.close()

threedim()
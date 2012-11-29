from migen.fhdl.structure import *
from migen.bus import csr
from migen.bank.description import *

class Bank:
	def __init__(self, description, address=0, interface=None):
		self.description = description
		self.address = address
		if interface is None:
			interface = csr.Interface()
		self.interface = interface
	
	def get_fragment(self):
		comb = []
		sync = []
		
		sel = Signal()
		comb.append(sel.eq(self.interface.adr[9:] == self.address))
		
		desc_exp = expand_description(self.description, csr.data_width)
		nbits = bits_for(len(desc_exp)-1)
		
		# Bus writes
		bwcases = {}
		for i, reg in enumerate(desc_exp):
			if isinstance(reg, RegisterRaw):
				comb.append(reg.r.eq(self.interface.dat_w[:reg.size]))
				comb.append(reg.re.eq(sel & \
					self.interface.we & \
					(self.interface.adr[:nbits] == i)))
			elif isinstance(reg, RegisterFields):
				bwra = []
				offset = 0
				for field in reg.fields:
					if field.access_bus == WRITE_ONLY or field.access_bus == READ_WRITE:
						bwra.append(field.storage.eq(self.interface.dat_w[offset:offset+field.size]))
					offset += field.size
				if bwra:
					bwcases[i] = bwra
				# commit atomic writes
				for field in reg.fields:
					if isinstance(field, FieldAlias) and field.commit_list:
						commit_instr = [hf.commit_to.eq(hf.storage) for hf in field.commit_list]
						sync.append(If(sel & self.interface.we & self.interface.adr[:nbits] == i, *commit_instr))
			else:
				raise TypeError
		if bwcases:
			sync.append(If(sel & self.interface.we, Case(self.interface.adr[:nbits], bwcases)))
		
		# Bus reads
		brcases = {}
		for i, reg in enumerate(desc_exp):
			if isinstance(reg, RegisterRaw):
				brcases[i] = [self.interface.dat_r.eq(reg.w)]
			elif isinstance(reg, RegisterFields):
				brs = []
				reg_readable = False
				for field in reg.fields:
					if field.access_bus == READ_ONLY or field.access_bus == READ_WRITE:
						brs.append(field.storage)
						reg_readable = True
					else:
						brs.append(Replicate(0, field.size))
				if reg_readable:
					brcases[i] = [self.interface.dat_r.eq(Cat(*brs))]
			else:
				raise TypeError
		if brcases:
			sync.append(self.interface.dat_r.eq(0))
			sync.append(If(sel, Case(self.interface.adr[:nbits], brcases)))
		else:
			comb.append(self.interface.dat_r.eq(0))
		
		# Device access
		for reg in self.description:
			if isinstance(reg, RegisterFields):
				for field in reg.fields:
					if field.access_bus == READ_ONLY and field.access_dev == WRITE_ONLY:
						comb.append(field.storage.eq(field.w))
					else:
						if field.access_dev == READ_ONLY or field.access_dev == READ_WRITE:
							comb.append(field.r.eq(field.storage))
						if field.access_dev == WRITE_ONLY or field.access_dev == READ_WRITE:
							sync.append(If(field.we, field.storage.eq(field.w)))
		
		return Fragment(comb, sync)

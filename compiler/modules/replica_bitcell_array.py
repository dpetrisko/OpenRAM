# See LICENSE for licensing information.
#
# Copyright (c) 2016-2019 Regents of the University of California
# All rights reserved.
#

import debug
import bitcell_base_array
from tech import drc, spice, cell_properties
from vector import vector
from globals import OPTS
from sram_factory import factory


class replica_bitcell_array(bitcell_base_array.bitcell_base_array):
    """
    Creates a bitcell arrow of cols x rows and then adds the replica
    and dummy columns and rows.  Replica columns are on the left and
    right, respectively and connected to the given bitcell ports.
    Dummy are the outside columns/rows with WL and BL tied to gnd.
    Requires a regular bitcell array, replica bitcell, and dummy
    bitcell (Bl/BR disconnected).
    """
    def __init__(self, rows, cols, rbl=None, left_rbl=None, right_rbl=None, name=""):
        super().__init__(name, rows, cols, column_offset=0)
        debug.info(1, "Creating {0} {1} x {2} rbls: {3} left_rbl: {4} right_rbl: {5}".format(self.name,
                                                                                             rows,
                                                                                             cols,
                                                                                             rbl,
                                                                                             left_rbl,
                                                                                             right_rbl))
        self.add_comment("rows: {0} cols: {1}".format(rows, cols))
        self.add_comment("rbl: {0} left_rbl: {1} right_rbl: {2}".format(rbl, left_rbl, right_rbl))

        self.column_size = cols
        self.row_size = rows
        # This is how many RBLs are in all the arrays
        if rbl:
            self.rbl = rbl
        else:
            self.rbl=[1, 1 if len(self.all_ports)>1 else 0]
        # This specifies which RBL to put on the left or right
        # by port number
        # This could be an empty list
        if left_rbl != None:
            self.left_rbl = left_rbl
        else:
            self.left_rbl = [0]
        # This could be an empty list
        if right_rbl != None:
            self.right_rbl = right_rbl
        else:
            self.right_rbl=[1] if len(self.all_ports) > 1 else []
        self.rbls = self.left_rbl + self.right_rbl
        
        debug.check(sum(self.rbl) == len(self.all_ports),
                    "Invalid number of RBLs for port configuration.")
        debug.check(sum(self.rbl) >= len(self.left_rbl) + len(self.right_rbl),
                    "Invalid number of RBLs for port configuration.")

        # Two dummy rows plus replica even if we don't add the column
        self.extra_rows = 2 + sum(self.rbl)
        # Two dummy cols plus replica if we add the column
        self.extra_cols = 2 + len(self.left_rbl) + len(self.right_rbl)

        self.create_netlist()
        if not OPTS.netlist_only:
            self.create_layout()

        # We don't offset this because we need to align
        # the replica bitcell in the control logic
        # self.offset_all_coordinates()
        
    def create_netlist(self):
        """ Create and connect the netlist """
        self.add_modules()
        self.add_pins()
        self.create_instances()

    def add_modules(self):
        """  Array and dummy/replica columns

        d or D = dummy cell (caps to distinguish grouping)
        r or R = replica cell (caps to distinguish grouping)
        b or B = bitcell
         replica columns 1
         v              v
        bdDDDDDDDDDDDDDDdb <- Dummy row
        bdDDDDDDDDDDDDDDrb <- Dummy row
        br--------------rb
        br|   Array    |rb
        br| row x col  |rb
        br--------------rb
        brDDDDDDDDDDDDDDdb <- Dummy row
        bdDDDDDDDDDDDDDDdb <- Dummy row

          ^^^^^^^^^^^^^^^
          dummy rows cols x 1

        ^ dummy columns  ^
          1 x (rows + 4)
        """
        # Bitcell array
        self.bitcell_array = factory.create(module_type="bitcell_array",
                                            column_offset=1 + len(self.left_rbl),
                                            cols=self.column_size,
                                            rows=self.row_size)
        self.add_mod(self.bitcell_array)

        # Replica bitlines
        self.replica_columns = {}
        
        for port in self.all_ports:
            if port in self.left_rbl:
                # We will always have self.rbl[0] rows of replica wordlines below
                # the array.
                # These go from the top (where the bitcell array starts ) down
                replica_bit = self.rbl[0] - port
            elif port in self.right_rbl:
                
                # We will always have self.rbl[0] rows of replica wordlines below
                # the array.
                # These go from the bottom up
                replica_bit = self.rbl[0] + self.row_size + port
            else:
                continue
            
            # If we have an odd numer on the bottom
            column_offset = self.rbl[0] + 1
                
            self.replica_columns[port] = factory.create(module_type="replica_column",
                                                        rows=self.row_size,
                                                        rbl=self.rbl,
                                                        column_offset=column_offset,
                                                        replica_bit=replica_bit)
            self.add_mod(self.replica_columns[port])
        try:
            end_caps_enabled = cell_properties.bitcell.end_caps
        except AttributeError:
            end_caps_enabled = False

        # Dummy row
        self.dummy_row = factory.create(module_type="dummy_array",
                                            cols=self.column_size,
                                            rows=1,
                                            # dummy column + left replica column
                                            column_offset=1 + len(self.left_rbl),
                                            mirror=0)
        self.add_mod(self.dummy_row)
        if not cell_properties.compare_ports(cell_properties.bitcell_array.use_custom_cell_arrangement):

            # Dummy Row or Col Cap, depending on bitcell array properties
            col_cap_module_type = ("col_cap_array" if end_caps_enabled else "dummy_array")
            self.col_cap = factory.create(module_type=col_cap_module_type,
                                          cols=self.column_size,
                                          rows=1,
                                          # dummy column + left replica column
                                          column_offset=1 + len(self.left_rbl),
                                          mirror=0)
            self.add_mod(self.col_cap)

            # Dummy Col or Row Cap, depending on bitcell array properties
            row_cap_module_type = ("row_cap_array" if end_caps_enabled else "dummy_array")

            self.row_cap_left = factory.create(module_type=row_cap_module_type,
                                                cols=1,
                                                column_offset=0,
                                                rows=self.row_size + self.extra_rows,
                                                mirror=(self.rbl[0] + 1) % 2)
            self.add_mod(self.row_cap_left)

            self.row_cap_right = factory.create(module_type=row_cap_module_type,
                                                cols=1,
                                                #   dummy column
                                                # + left replica column(s)
                                                # + bitcell columns
                                                # + right replica column(s)
                                                column_offset = 1 + len(self.left_rbl) + self.column_size + self.rbl[0],
                                                rows=self.row_size + self.extra_rows,
                                                mirror=(self.rbl[0] + 1) %2)
            self.add_mod(self.row_cap_right)
        else:
            # Dummy Row or Col Cap, depending on bitcell array properties
            col_cap_module_type = ("s8_col_cap_array" if end_caps_enabled else "dummy_array")
            self.col_cap_top = factory.create(module_type=col_cap_module_type,
                                        cols=self.column_size,
                                        rows=1,
                                        # dummy column + left replica column(s)
                                        column_offset=1 + len(self.left_rbl),
                                        mirror=0,
                                        location="top")
            self.add_mod(self.col_cap_top)

            self.col_cap_bottom = factory.create(module_type=col_cap_module_type,
                                                 cols=self.column_size,
                                                 rows=1,
                                                 # dummy column + left replica column(s)
                                                 column_offset=1 + len(self.left_rbl),
                                                 mirror=0,
                                                 location="bottom")
            self.add_mod(self.col_cap_bottom)
            # Dummy Col or Row Cap, depending on bitcell array properties
            row_cap_module_type = ("s8_row_cap_array" if end_caps_enabled else "dummy_array")

            self.row_cap_left = factory.create(module_type=row_cap_module_type,
                                                cols=1,
                                                column_offset=0,
                                                rows=self.row_size + self.extra_rows,
                                                mirror=0)
            self.add_mod(self.row_cap_left)

            self.row_cap_right = factory.create(module_type=row_cap_module_type,
                                                cols=1,
                                                #   dummy column
                                                # + left replica column(s)
                                                # + bitcell columns
                                                # + right replica column(s)
                                                column_offset = 1 + len(self.left_rbl) + self.column_size + self.rbl[0],
                                                rows=self.row_size + self.extra_rows,
                                                mirror=0)
            self.add_mod(self.row_cap_right)

    def add_pins(self):

        # Arrays are always:
        # bitlines (column first then port order)
        # word lines (row first then port order)
        # dummy wordlines
        # replica wordlines
        # regular wordlines (bottom to top)
        # # dummy bitlines
        # replica bitlines (port order)
        # regular bitlines (left to right port order)
        #
        # vdd
        # gnd
        
        self.add_bitline_pins()
        self.add_wordline_pins()
        self.add_pin("vdd", "POWER")
        self.add_pin("gnd", "GROUND")

    def add_bitline_pins(self):
        # The bit is which port the RBL is for
        for bit in self.rbls:
            for port in self.all_ports:
                self.rbl_bitline_names[bit].append("rbl_bl_{0}_{1}".format(port, bit))
            for port in self.all_ports:
                self.rbl_bitline_names[bit].append("rbl_br_{0}_{1}".format(port, bit))
        # Make a flat list too
        self.all_rbl_bitline_names = [x for sl in self.rbl_bitline_names for x in sl]

        self.bitline_names = self.bitcell_array.bitline_names
        # Make a flat list too
        self.all_bitline_names = [x for sl in zip(*self.bitline_names) for x in sl]

        for port in self.left_rbl:
            self.add_pin_list(self.rbl_bitline_names[port], "INOUT")
        self.add_pin_list(self.all_bitline_names, "INOUT")
        for port in self.right_rbl:
            self.add_pin_list(self.rbl_bitline_names[port], "INOUT")
        
    def add_wordline_pins(self):

        # Wordlines to ground
        self.gnd_wordline_names = []

        for port in self.all_ports:
            for bit in self.all_ports:
                self.rbl_wordline_names[port].append("rbl_wl_{0}_{1}".format(port, bit))
                if bit != port:
                    self.gnd_wordline_names.append("rbl_wl_{0}_{1}".format(port, bit))

        self.all_rbl_wordline_names = [x for sl in self.rbl_wordline_names for x in sl]

        self.wordline_names = self.bitcell_array.wordline_names
        self.all_wordline_names = self.bitcell_array.all_wordline_names
 

        # All wordlines including dummy and RBL
        self.replica_array_wordline_names = []
        if not cell_properties.compare_ports(cell_properties.bitcell_array.use_custom_cell_arrangement):
            self.replica_array_wordline_names.extend(["gnd"] * len(self.col_cap.get_wordline_names()))
        for bit in range(self.rbl[0]):
            self.replica_array_wordline_names.extend([x if x not in self.gnd_wordline_names else "gnd" for x in self.rbl_wordline_names[bit]])
        self.replica_array_wordline_names.extend(self.all_wordline_names)
        for bit in range(self.rbl[1]):
            self.replica_array_wordline_names.extend([x if x not in self.gnd_wordline_names else "gnd" for x in self.rbl_wordline_names[self.rbl[0] + bit]])
        if not cell_properties.compare_ports(cell_properties.bitcell_array.use_custom_cell_arrangement):
            self.replica_array_wordline_names.extend(["gnd"] * len(self.col_cap.get_wordline_names()))

        for port in range(self.rbl[0]):
            self.add_pin(self.rbl_wordline_names[port][port], "INPUT")
        self.add_pin_list(self.all_wordline_names, "INPUT")
        for port in range(self.rbl[0], self.rbl[0] + self.rbl[1]):
            self.add_pin(self.rbl_wordline_names[port][port], "INPUT")

    def create_instances(self):
        """ Create the module instances used in this design """
        if not cell_properties.compare_ports(cell_properties.bitcell_array.use_custom_cell_arrangement):

            self.supplies = ["vdd", "gnd"]

            # Used for names/dimensions only
            self.cell = factory.create(module_type="bitcell")

            # Main array
            self.bitcell_array_inst=self.add_inst(name="bitcell_array",
                                                    mod=self.bitcell_array)
            self.connect_inst(self.all_bitline_names + self.all_wordline_names + self.supplies)

            # Replica columns
            self.replica_col_insts = []
            for port in self.all_ports:
                if port in self.rbls:
                    self.replica_col_insts.append(self.add_inst(name="replica_col_{}".format(port),
                                                                mod=self.replica_columns[port]))
                    self.connect_inst(self.rbl_bitline_names[port] + self.replica_array_wordline_names + self.supplies)
                else:
                    self.replica_col_insts.append(None)
                    
            # Dummy rows under the bitcell array (connected with with the replica cell wl)
            self.dummy_row_replica_insts = []
            # Note, this is the number of left and right even if we aren't adding the columns to this bitcell array!
            for port in self.all_ports:
                self.dummy_row_replica_insts.append(self.add_inst(name="dummy_row_{}".format(port),
                                                                    mod=self.dummy_row))
                self.connect_inst([x if x not in self.gnd_wordline_names else "gnd" for x in self.rbl_wordline_names[port]] + self.supplies)

            # Top/bottom dummy rows or col caps
            self.dummy_row_insts = []
            self.dummy_row_insts.append(self.add_inst(name="dummy_row_bot",
                                                      mod=self.col_cap))
            self.connect_inst(["gnd"] * len(self.col_cap.get_wordline_names()) + self.supplies)
            self.dummy_row_insts.append(self.add_inst(name="dummy_row_top",
                                                      mod=self.col_cap))
            self.connect_inst(["gnd"] * len(self.col_cap.get_wordline_names()) + self.supplies)

            # Left/right Dummy columns
            self.dummy_col_insts = []
            self.dummy_col_insts.append(self.add_inst(name="dummy_col_left",
                                                      mod=self.row_cap_left))
            self.connect_inst(self.replica_array_wordline_names + self.supplies)
            self.dummy_col_insts.append(self.add_inst(name="dummy_col_right",
                                                      mod=self.row_cap_right))
            self.connect_inst(self.replica_array_wordline_names + self.supplies)
        else:
            from tech import custom_replica_bitcell_array_arrangement
            custom_replica_bitcell_array_arrangement(self)

    def create_layout(self):

        # We will need unused wordlines grounded, so we need to know their layer
        pin = self.cell.get_pin(self.cell.get_all_wl_names()[0])
        pin_layer = pin.layer
        self.unused_pitch = 1.5 * getattr(self, "{}_pitch".format(pin_layer))
        self.unused_offset = vector(self.unused_pitch, 0)

        # Add extra width on the left and right for the unused WLs
        if not cell_properties.compare_ports(cell_properties.bitcell_array.use_custom_cell_arrangement):
            self.height = (self.row_size + self.extra_rows) * self.dummy_row.height
            self.width = (self.column_size + self.extra_cols) * self.cell.width + 2 * self.unused_pitch
        else:
            self.width = self.row_cap_left.width + self.row_cap_right.width + self.col_cap_top.width
            for rbl in range(self.rbl[0] + self.rbl[1]):
                self.width += self.replica_col_insts[rbl].width
            self.height = self.row_cap_left.height


        # This is a bitcell x bitcell offset to scale
        self.bitcell_offset = vector(self.cell.width, self.cell.height)
        if not cell_properties.compare_ports(cell_properties.bitcell_array.use_custom_cell_arrangement):
            self.strap_offset = vector(0, 0)
            self.col_end_offset = vector(self.cell.width, self.cell.height)
            self.row_end_offset = vector(self.cell.width, self.cell.height)
        else:
            self.strap_offset = vector(self.replica_col_insts[0].mod.strap1.width, self.replica_col_insts[0].mod.strap1.height)
            self.col_end_offset = vector(self.dummy_row_insts[0].mod.colend1.width, self.dummy_row_insts[0].mod.colend1.height)
            self.row_end_offset = vector(self.dummy_col_insts[0].mod.rowend1.width, self.dummy_col_insts[0].mod.rowend1.height)

        # Everything is computed with the main array at (self.unused_pitch, 0) to start
        self.bitcell_array_inst.place(offset=self.unused_offset)

        self.add_replica_columns()
        
        self.add_end_caps()


        # Array was at (0, 0) but move everything so it is at the lower left
        # We move DOWN the number of left RBL even if we didn't add the column to this bitcell array
        array_offset = self.bitcell_offset.scale(1 + len(self.left_rbl), 1 + self.rbl[0])
        self.translate_all(array_offset.scale(-1, -1))

        self.add_layout_pins()

        self.route_unused_wordlines()
        
        self.add_boundary()

        self.DRC_LVS()

    def get_main_array_top(self):
        return self.bitcell_array_inst.uy()

    def get_main_array_bottom(self):
        return self.bitcell_array_inst.by()

    def get_main_array_left(self):
        return self.bitcell_array_inst.lx()

    def get_main_array_right(self):
        return self.bitcell_array_inst.rx()

    def get_column_offsets(self):
        """
        Return an array of the x offsets of all the regular bits
        """
        offsets = [x + self.bitcell_array_inst.lx() for x in self.bitcell_array.get_column_offsets()]
        return offsets

    def add_replica_columns(self):
        """ Add replica columns on left and right of array """
        try:
            end_caps_enabled = cell_properties.bitcell.end_caps
        except AttributeError:
            end_caps_enabled = False

        # Grow from left to right, toward the array
        for bit, port in enumerate(self.left_rbl):
            if not end_caps_enabled:
                offset = self.bitcell_offset.scale(-len(self.left_rbl) + bit, -self.rbl[0] - 1) + self.strap_offset.scale(-len(self.left_rbl) + bit, 0) + self.unused_offset
            else:
                offset = self.bitcell_offset.scale(-len(self.left_rbl) + bit, -self.rbl[0] - (self.col_end_offset.y/self.cell.height)) + self.strap_offset.scale(-len(self.left_rbl) + bit, 0) + self.unused_offset

            self.replica_col_insts[bit].place(offset)
        # Grow to the right of the bitcell array, array outward
        for bit, port in enumerate(self.right_rbl):
            if not end_caps_enabled:
                offset = self.bitcell_array_inst.lr() + self.bitcell_offset.scale(bit, -self.rbl[0] - 1) + self.strap_offset.scale(bit, -self.rbl[0] - 1)
            else:
                offset = self.bitcell_array_inst.lr() + self.bitcell_offset.scale(bit, -self.rbl[0] - (self.col_end_offset.y/self.cell.height)) + self.strap_offset.scale(bit, -self.rbl[0] - 1)

            self.replica_col_insts[self.rbl[0] + bit].place(offset)

        # Replica dummy rows
        # Add the dummy rows even if we aren't adding the replica column to this bitcell array
        # These grow up, toward the array
        for bit in range(self.rbl[0]):
            dummy_offset = self.bitcell_offset.scale(0, -self.rbl[0] + bit + (-self.rbl[0] + bit) % 2) + self.unused_offset
            self.dummy_row_replica_insts[bit].place(offset=dummy_offset,
                                                    mirror="MX" if (-self.rbl[0] + bit) % 2 else "R0")
        # These grow up, away from the array
        for bit in range(self.rbl[1]):
            dummy_offset = self.bitcell_offset.scale(0, bit + bit % 2) + self.bitcell_array_inst.ul()
            self.dummy_row_replica_insts[self.rbl[0] + bit].place(offset=dummy_offset,
                                                                  mirror="MX" if bit % 2 else "R0")
        
    def add_end_caps(self):
        """ Add dummy cells or end caps around the array """
        try:
            end_caps_enabled = cell_properties.bitcell.end_caps
        except AttributeError:
            end_caps_enabled = False

        # FIXME: These depend on the array size itself
        # Far top dummy row (first row above array is NOT flipped)
        flip_dummy = self.rbl[1] % 2
        if not end_caps_enabled:
            dummy_row_offset = self.bitcell_offset.scale(0,  self.rbl[1] + flip_dummy) + self.bitcell_array_inst.ul()
        else:
            dummy_row_offset = self.bitcell_offset.scale(0,  self.rbl[1] + flip_dummy) + self.bitcell_array_inst.ul()

        self.dummy_row_insts[1].place(offset=dummy_row_offset,
                                      mirror="MX" if flip_dummy else "R0")
        # FIXME: These depend on the array size itself
        # Far bottom dummy row (first row below array IS flipped)
        flip_dummy = (self.rbl[0] + 1) % 2
        if not end_caps_enabled:
            dummy_row_offset = self.bitcell_offset.scale(0, -self.rbl[0] - 1 + flip_dummy) + self.unused_offset
        else:
             dummy_row_offset = self.bitcell_offset.scale(0, -self.rbl[0] - (self.col_end_offset.y/self.cell.height) + flip_dummy) + self.unused_offset
        self.dummy_row_insts[0].place(offset=dummy_row_offset,
                                          mirror="MX" if flip_dummy else "R0")
        # Far left dummy col
        # Shifted down by the number of left RBLs even if we aren't adding replica column to this bitcell array
        if not end_caps_enabled:
            dummy_col_offset = self.bitcell_offset.scale(-len(self.left_rbl) - 1, -self.rbl[0] - 1)  + self.unused_offset
        else:
            dummy_col_offset = self.bitcell_offset.scale(-(len(self.left_rbl)*(1+self.strap_offset.x/self.cell.width)) - (self.row_end_offset.x/self.cell.width), -len(self.left_rbl) - (self.col_end_offset.y/self.cell.height))

        self.dummy_col_insts[0].place(offset=dummy_col_offset)
        # Far right dummy col
        # Shifted down by the number of left RBLs even if we aren't adding replica column to this bitcell array
        if not end_caps_enabled:
            dummy_col_offset = self.bitcell_offset.scale(len(self.right_rbl), -self.rbl[0] - 1) + self.bitcell_array_inst.lr()
        else:
            dummy_col_offset = self.bitcell_offset.scale(len(self.right_rbl)*(1+self.strap_offset.x/self.cell.width), -self.rbl[0] - (self.col_end_offset.y/self.cell.height)) + self.bitcell_array_inst.lr()

        self.dummy_col_insts[1].place(offset=dummy_col_offset)

    def add_layout_pins(self):
        """ Add the layout pins """
        
        #All wordlines
        #Main array wl and bl/br
        if not cell_properties.compare_ports(cell_properties.bitcell_array.use_custom_cell_arrangement):

            for pin_name in self.all_wordline_names:
                pin_list = self.bitcell_array_inst.get_pins(pin_name)
                for pin in pin_list:
                    self.add_layout_pin(text=pin_name,
                                        layer=pin.layer,
                                        offset=pin.ll().scale(0, 1),
                                        width=self.width,
                                        height=pin.height())
            # Replica wordlines (go by the row instead of replica column because we may have to add a pin
            # even though the column is in another local bitcell array)
            for (names, inst) in zip(self.rbl_wordline_names, self.dummy_row_replica_insts):
                for (wl_name, pin_name) in zip(names, self.dummy_row.get_wordline_names()):
                    if wl_name in self.gnd_wordline_names:
                        continue
                    pin = inst.get_pin(pin_name)
                    self.add_layout_pin(text=wl_name,
                                        layer=pin.layer,
                                        offset=pin.ll().scale(0, 1),
                                        width=self.width,
                                        height=pin.height())
        else:
            for pin_name in self.all_wordline_names:
                pin_list = self.dummy_col_insts[0].get_pins(pin_name)
                for pin in pin_list:
                    self.add_layout_pin(text=pin_name,
                                        layer=pin.layer,
                                        offset=pin.ll().scale(0, 1),
                                        width=self.width,
                                        height=pin.height())
            # Replica wordlines (go by the row instead of replica column because we may have to add a pin
            # even though the column is in another local bitcell array)
            for (names, inst) in zip(self.rbl_wordline_names, self.dummy_row_replica_insts):
                for (wl_name, pin_name) in zip(names, self.dummy_row.get_wordline_names()):
                    if wl_name in self.gnd_wordline_names:
                        continue
                    pin = inst.get_pin(pin_name)
                    self.add_layout_pin(text=wl_name,
                                        layer=pin.layer,
                                        offset=pin.ll().scale(0, 1),
                                        width=self.width,
                                        height=pin.height())
                                        
        for pin_name in self.all_bitline_names:
            pin_list = self.bitcell_array_inst.get_pins(pin_name)
            for pin in pin_list:
                self.add_layout_pin(text=pin_name,
                                    layer=pin.layer,
                                    offset=pin.ll().scale(1, 0),
                                    width=pin.width(),
                                    height=self.height)

        # Replica bitlines
        if len(self.rbls) > 0:
            for (names, inst) in zip(self.rbl_bitline_names, self.replica_col_insts):
                pin_names = self.replica_columns[self.rbls[0]].all_bitline_names
                for (bl_name, pin_name) in zip(names, pin_names):
                    pin = inst.get_pin(pin_name)
                    self.add_layout_pin(text=bl_name,
                                        layer=pin.layer,
                                        offset=pin.ll().scale(1, 0),
                                        width=pin.width(),
                                        height=self.height)

        # vdd/gnd are only connected in the perimeter cells
        # replica column should only have a vdd/gnd in the dummy cell on top/bottom
        supply_insts = self.dummy_col_insts + self.dummy_row_insts
        
        for pin_name in  self.supplies:
            for inst in supply_insts:
                pin_list = inst.get_pins(pin_name)
                for pin in pin_list:
                    self.add_power_pin(name=pin_name,
                                       loc=pin.center(),
                                       start_layer=pin.layer)

            for inst in self.replica_col_insts:
                if inst:
                    self.copy_layout_pin(inst, pin_name)

    def analytical_power(self, corner, load):
        """Power of Bitcell array and bitline in nW."""
        # Dynamic Power from Bitline
        bl_wire = self.gen_bl_wire()
        cell_load = 2 * bl_wire.return_input_cap()
        bl_swing = OPTS.rbl_delay_percentage
        freq = spice["default_event_frequency"]
        bitline_dynamic = self.calc_dynamic_power(corner, cell_load, freq, swing=bl_swing)

        # Calculate the bitcell power which currently only includes leakage
        cell_power = self.cell.analytical_power(corner, load)

        # Leakage power grows with entire array and bitlines.
        total_power = self.return_power(cell_power.dynamic + bitline_dynamic * self.column_size,
                                        cell_power.leakage * self.column_size * self.row_size)
        return total_power

    def route_unused_wordlines(self):
        """ Connect the unused RBL and dummy wordlines to gnd """
        if not cell_properties.compare_ports(cell_properties.bitcell_array.use_custom_cell_arrangement):
            # This grounds all the dummy row word lines
            for inst in self.dummy_row_insts:
                for wl_name in self.col_cap.get_wordline_names():
                    self.ground_pin(inst, wl_name)

            # Ground the unused replica wordlines
            for (names, inst) in zip(self.rbl_wordline_names, self.dummy_row_replica_insts):
                for (wl_name, pin_name) in zip(names, self.dummy_row.get_wordline_names()):
                    if wl_name in self.gnd_wordline_names:
                        self.ground_pin(inst, pin_name)

    def ground_pin(self, inst, name):
        pin = inst.get_pin(name)
        pin_layer = pin.layer
        
        left_pin_loc = vector(self.dummy_col_insts[0].lx(), pin.cy())
        right_pin_loc = vector(self.dummy_col_insts[1].rx(), pin.cy())

        # Place the pins a track outside of the array
        left_loc = left_pin_loc - vector(self.unused_pitch, 0)
        right_loc = right_pin_loc + vector(self.unused_pitch, 0)
        self.add_power_pin("gnd", left_loc, directions=("H", "H"))
        self.add_power_pin("gnd", right_loc, directions=("H", "H"))

        # Add a path to connect to the array
        self.add_path(pin_layer, [left_loc, left_pin_loc])
        self.add_path(pin_layer, [right_loc, right_pin_loc])
        
    def gen_bl_wire(self):
        if OPTS.netlist_only:
            height = 0
        else:
            height = self.height
        bl_pos = 0
        bl_wire = self.generate_rc_net(int(self.row_size - bl_pos), height, drc("minwidth_m1"))
        bl_wire.wire_c =spice["min_tx_drain_c"] + bl_wire.wire_c # 1 access tx d/s per cell
        return bl_wire

    def graph_exclude_bits(self, targ_row=None, targ_col=None):
        """
        Excludes bits in column from being added to graph except target
        """
        self.bitcell_array.graph_exclude_bits(targ_row, targ_col)

    def graph_exclude_replica_col_bits(self):
        """
        Exclude all replica/dummy cells in the replica columns except the replica bit.
        """

        for port in self.left_rbl + self.right_rbl:
            self.replica_columns[port].exclude_all_but_replica()

    def get_cell_name(self, inst_name, row, col):
        """
        Gets the spice name of the target bitcell.
        """
        return self.bitcell_array.get_cell_name(inst_name + '.x' + self.bitcell_array_inst.name, row, col)

    def clear_exclude_bits(self):
        """ 
        Clears the bit exclusions
        """
        self.bitcell_array.init_graph_params()

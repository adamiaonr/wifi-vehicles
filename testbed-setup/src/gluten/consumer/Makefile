# set the main compiler here. Options e.g.: 'gcc', 'g++'
CC := arm-openwrt-linux-muslgnueabi-gcc
#CC := gcc
# directories
SRCDIR := .
BUILDDIR := build
TARGET := consumer

SRCEXT := c
SOURCES := $(shell find $(SRCDIR) -type f -name *.$(SRCEXT))
OBJECTS := $(patsubst $(SRCDIR)/%,$(BUILDDIR)/%,$(SOURCES:.$(SRCEXT)=.o))

# use -ggdb for GNU debugger
# CFLAGS := -g -ggdb -gdwarf-2 -Wall -Wno-comment -std=c11
LD := arm-openwrt-linux-muslgnueabi-ld
INC := -I ~/workbench/lede-ad7200/staging_dir/target-arm_cortex-a15+neon-vfpv4_musl-1.1.16_eabi/usr/include ~/workbench/lede-ad7200/staging_dir/target-arm_cortex-a15+neon-vfpv4_musl-1.1.16_eabi/usr/lib
#INC := -Iinclude
CFLAGS := -O2 -Wall -Wno-comment -std=c11 -static

#all: $(TARGET) $(TARGET)
all: $(TARGET)
	@echo " Doing nothing..."

$(TARGET): $(OBJECTS)
	@echo " Linking..."
	@echo " $(CC) $^ -o $(TARGET) $(LIB)"; $(CC) $^ -o $(TARGET) $(LIB)

$(BUILDDIR)/%.o: $(SRCDIR)/%.$(SRCEXT)
	@mkdir -p $(BUILDDIR)
	@echo " $(CC) $(CFLAGS) $(INC) -c -o $@ $<"; $(CC) $(CFLAGS) $(INC) -c -o $@ $<

clean:
	@echo " Cleaning..."; 
	$(RM) -r $(BUILDDIR) $(TARGET) *~

.PHONY: clean

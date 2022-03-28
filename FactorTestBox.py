import pandas as pd
import numpy as np
from math import *
from scipy.stats import norm
from scipy.special import erfinv
#import QuantLib as ql
import matplotlib.pyplot as plt
#import statsmodels.api as sm
import scipy
import scipy.stats as stats
import os
import pymysql
import cx_Oracle
import pickle
import sys
import seaborn
import time
from tqdm import tqdm
import h5py
import warnings
from FactorTest.FactorTestPara import *
warnings.filterwarnings('ignore')
import pyarrow.feather as feather
import datetime
#设置图片保存格式和字体
import matplotlib as mpl
mpl.rcParams['font.sans-serif'] = ['PingFang HK']  # 设置默认字体
mpl.rcParams['axes.unicode_minus'] = False #解决保存图像是负号显示为方块问题
#读入pickle文件
def read_pickle(filename):
    with open(filename, 'rb') as f:
        sql_data = pickle.load(f)
    return sql_data
def save_pickle(filename,data):
    with open(filename,'wb') as f:
        '''
            保存pickle文件到指定目录，这里每次保存前先将pickle清空
            当保存dict文件的时候，需要设置highest_protocal=True
            '''
        pick=pickle.Pickler(f)
        pick.clear_memo()
        pick.dump(data)
def read_feather(filename):
    sql_data = feather.read_feather(filename)
    return sql_data
def save_feather(filename,data):
    """
    注意：要求存储内容保持一致
    """
    feather.write_feather(data,filename)
# 保存hdf5文件，格式可以是df,也可以是很多df构成的dict，只支持一层嵌套
def save_hdf5(df_or_dict,file_full_root,subgroup=None):
    '''
    保存hdf5文件，格式可以是df,也可以是很多df构成的dict，只支持一层嵌套
    :param df_or_dict: 一个df或者dict{df}
    :param file_full_root: h5文件的全路径
    :param subgroup: 如果是None，则保存在hdf5文件最外层的目录下，否则，整个df或者dict保存在对应的subgroup内
                     如果输入的是dict,那么保存在subgroup内，如果输入的是df，则将df保存在对应的subgroup内
    :return:
    '''
    file_h = pd.HDFStore(file_full_root,'a')
    file_keys_raw = file_h.keys()
    file_keys = [x[1:] for x in file_keys_raw]
    file_h.close()
    if isinstance(df_or_dict,pd.DataFrame) or isinstance(df_or_dict,pd.Series):
        if subgroup is None:
            df_or_dict.to_hdf(file_full_root,key='_data')
        else:
            df_or_dict.to_hdf(file_full_root,key=subgroup)
    elif isinstance(df_or_dict,dict):
        file_h = pd.HDFStore(file_full_root, 'a')
        if subgroup is None:
            for sub_df_name in df_or_dict:
                file_h[sub_df_name] = df_or_dict[sub_df_name]
        else:
            for sub_df_name in df_or_dict:
                file_h[subgroup][sub_df_name] = df_or_dict[sub_df_name]
        file_h.close()
    else:
        raise Exception('wrong input type, only df or dict{df} supported!')
    print(file_full_root+' save finished!')
# 读取hdf5文件，h5文件可以是里面['_data']是df，也可以是一整个dict{df},或者选定要读取哪个subgroup
def read_hdf5(file_full_root,subgroup=None):
    if os.path.exists(file_full_root):
        file_h = pd.HDFStore(file_full_root,'r')
        file_keys_raw = file_h.keys()
        file_keys = [x[1:] for x in file_keys_raw]
        if len(file_keys)==1 and subgroup is None:
            result = file_h[file_keys[0]]
        elif len(file_keys)==1 and subgroup is not None:
            if subgroup in file_keys:
                result = file_h[subgroup]
            else:
                result = pd.DataFrame()
        elif len(file_keys)>1 and subgroup is not None:
            try:
                result = file_h[subgroup]
            except:
                result = pd.DataFrame()
        elif len(file_keys)>1 and subgroup is None:
            result = {}
            for i in file_keys:
                result[i] = file_h[i]
        else:
            # 原始文件是空的
            if subgroup is not None:
                result = pd.DataFrame()
            else:
                result = None
        file_h.close()
    else:
        result = None
    return result


# 从东吴在线落地数据库提取数据
def getSql(sql_req):
    """

    @param sql_req:sql代码
    @return:DF格式
    """
    os.environ['NLS_LANG'] = 'SIMPLIFIED CHINESE_CHINA.UTF8'
    Oracle_userName = 'sjcj'
    Oracle_password = 'dwzqsjcj'
    Oracle_sid = 'sidwdzx1'
    Oracle_ip = '222.92.214.61'
    Oracle_port = '20001'
    dsn_tns = cx_Oracle.makedsn(Oracle_ip, Oracle_port, Oracle_sid)
    db_oracle = cx_Oracle.connect(Oracle_userName, Oracle_password, dsn_tns)
    data = pd.read_sql(sql_req, con=db_oracle)
    return data
#计算最大回撤
def maxDrawDown(return_list):
    """
    求最大回撤率
    #param return_list:Series格式月度收益率
    #return：0~1

    """
    return_list=list((return_list+1).cumprod())
    i = np.argmax((np.maximum.accumulate(return_list) - return_list) / np.maximum.accumulate(return_list))  # 结束位置
    if i == 0:
        return 0
    j = np.argmax(return_list[:i])  # 开始位置
    return (return_list[i] - return_list[j]) / (return_list[j])
#修改——自动多样式
def to_time(x,timetype='%Y%m%d'):
    return pd.Series(x).apply(lambda x:datetime.datetime.strptime(str(int(x)),timetype))
#回归：x可以选择是否加截距项
def regress(y,x,con=True):
    """
    回归——注意不能出现空值
    @param y:   应变量
    @param x:   自变量
    @param con: 是否加入截距项（涉及到行业信息的不加）
    @return: 返回res  残差：res.resid
    """
    import statsmodels.api as sm # 最小二乘
    from statsmodels.stats.outliers_influence import summary_table # 获得汇总信息
    if(con):
        x=sm.add_constant(x)
    regr = sm.OLS(y, x) # 普通最小二乘模型，ordinary least square model
    res = regr.fit()    #res.model.endog
    # 从模型获得拟合数据
    st, data, ss2 = summary_table(res, alpha=0.05) # 置信水平alpha=5%，st数据汇总，data数据详情，ss2数据列名
    fitted_values = data[:,2]  #等价于res.fittedvalues
    return res
#更新数据 获得最新交易日历、计算收益序列数据  输出到一张表中：各指标最新日期
def updateStockDailyRet():
    close=read_feather(Datapath+'BasicFactor_Close.txt').set_index('time')
    adjfactor=read_feather(Datapath+'BasicFactor_AdjFactor.txt').set_index('time')
    adjclose=close*adjfactor
    adjopen=read_feather(Datapath+'BasicFactor_Open.txt').set_index('time')*adjfactor
    
    adjclose=adjclose.reset_index().fillna(method='ffill')
    adjclose['time']=adjclose['time'].apply(lambda x:int(str(x)[:6]))
    adjclose=adjclose.drop_duplicates(subset=['time'],keep='last').set_index('time')

    adjopen=adjopen.reset_index()
    adjopen['time']=adjopen['time'].apply(lambda x:int(str(x)[:6]))
    adjopen=adjopen.drop_duplicates(subset=['time'],keep='first').set_index('time')

    adjclose=adjclose/adjopen-1

    adjclose=adjclose.stack().reset_index()   
    adjclose.columns=['time','code','ret']
    def shift1(x):
        x=int(x)-1
        if(x%100==0):
            x=x-88
        return x  
    adjclose['time']=adjclose['time'].apply(shift1)
    adjclose=kickout(adjclose)
    adjclose.to_csv(filepathtestdata+'stockret.csv')
#获得交易日历
def getTradeDateList(period='date'):
    data=read_feather(Datapath+'BasicFactor_close.txt')
    if(period=='date'):
        return data['time']
    elif(period=='month'):
        return pd.Series(data['time'].apply(lambda x:int(str(x)[:6])).unique(),name='time')

#获取股票序列
def getStockList():
    data=read_feather(Datapath+'BasicFactor_close.txt').set_index('time')
    return pd.Series(data.columns,name='code')
#获取收益序列数据
def getRetData():
    retData=pd.read_csv(filepathtestdata+'stockret.csv',usecols=[1,2,3]).dropna()
    return retData

#读取指数行情数据 改 缺指数收益数据
def getIndexData(code):
    """
    code=["000300.SH",'000905.SH','000985.SH']
    """
    indexData=pd.read_csv(filepathtestdata+'index_data.csv',index_col=0)
    indexData.columns=['code','time','ret']
    indexData=indexData[indexData.code==code]
    indexData=indexData.sort_values(by='time')
    return indexData
#读取指数成分股列表 改  缺 500、1000成分股数据
def getIndexComponent(indexname='wind'):
    """
     indexname={300,500,800,1000}
    """
    if(indexname=='wind'):
        IndexComponent=readLocalData('WINDAComponent.txt').dropna()
    if(indexname==300):
        IndexComponent=readLocalData('HS300Component.txt').dropna()
    if(indexname==500):
        IndexComponent=readLocalData('CSI500Component.txt').dropna().reset_index(drop=True)
    if(indexname==800):
        IndexComponent=readLocalData('HS300Component.txt').dropna().reset_index(drop=True)
        IndexComponent1=readLocalData('CSI500Component.txt').dropna().reset_index(drop=True)
        IndexComponent=IndexComponent.append(IndexComponent1)
    if(indexname==1000):
        IndexComponent=readLocalData('CSI1000Component.txt').dropna().reset_index(drop=True)
    IndexComponent['time']=IndexComponent['time'].apply(lambda x:int(str(x)[:6]))
    IndexComponent=IndexComponent.drop_duplicates(subset=['time','code'],keep='last')
    return IndexComponent

#筛选股票 
def setStockPool(DF,DFfilter):
    """
    stockpool = ["000300.SH",'000905.SH','000985.SH']
    参数：DF  columns=[code,date,xx]
    """
    DF=DF.merge(DFfilter[['time','code']],on=['code','time'])
    return DF

#得到申万行业分类数据 
def getIndustryData(level=1,freq='day',fill=False):
    """
        startdate 格式例20200731  缺失则代表不加限制
    """
    ind_data=pd.read_feather(Datapath+r'\BasicFactor_Swind_Component.txt')
    if(freq=='month'):
        ind_data['time']=ind_data['time'].apply(lambda x:int(str(x)[:6]))
        ind_data=ind_data.fillna(method='ffill').drop_duplicates(['time'],keep='last')
    ind_data=ind_data.set_index('time')
    ind_data=ind_data.stack().reset_index()
    ind_data.columns=['time','code','SWind']
    if(level==1):
        ind_data['SWind']=ind_data['SWind'].apply(lambda x:str(x)[:4])
    if(level==2):
        ind_data['SWind']=ind_data['SWind'].apply(lambda x:str(x)[:6])
    if(fill==False):
        return ind_data
    ind_data=ind_data.sort_values(by='time')
    ind_data=ind_data.pivot(index='time',columns='code',values=['SWind'])
    ind_data=ind_data.reindex(getTradeDateList()).fillna(method='ffill').stack().reset_index()
    return ind_data
#加上行业数据列 
def getSWIndustry(DF,level=1):
    """
        level 1 申万一级行业
    """
    SWData=getIndustryData(level)
    DF=DF.merge(SWData,on=['time','code'],how='left')
    return DF


#合并大类行业  待改(直接改到数据更新模块)
def industryAggregate(IndInfo):
    """
        六个行业大类 消费 能源 周期 金融 TMT 其他
    """
    IndustryAggregationInfo=pd.Series(index=['纺织服装', '家用电器', '商业贸易', '农林牧渔', '食品饮料', '休闲服务', '医药生物','银行','非银金融','钢铁','有色金属','采掘','化工','建筑材料','建筑装饰','电气设备','机械设备','轻工制造','国防军工','汽车','公用事业','电子','通信','计算机','传媒','综合','房地产','交通运输'])
    IndustryAggregationInfo[['纺织服装', '家用电器', '商业贸易', '农林牧渔', '食品饮料', '休闲服务', '医药生物']]='消费'
    IndustryAggregationInfo[['钢铁','有色金属','采掘']]='能源冶金'
    IndustryAggregationInfo[['化工','建筑材料','建筑装饰','电气设备','机械设备','轻工制造','国防军工','汽车','公用事业']]='工业周期'
    IndustryAggregationInfo[['银行','非银金融']]='金融'
    IndustryAggregationInfo[['电子','通信','计算机','传媒']]='TMT'
    IndustryAggregationInfo[['综合','房地产','交通运输']]='其它'
    for ind in IndustryAggregationInfo.index:
        IndInfo.loc[IndInfo['SW1']==ind,'IndC']=IndustryAggregationInfo[ind]
    del IndInfo['SW1']
    return IndInfo

#读取barra因子
def getBarraData(startdate='',enddate=''):
    """
        startdate 格式例20200731 int
        返回DataFrame  time code barra factor (注:日频)
    """
    BarraData = read_hdf5(filepathtestdata + 'FactorLoading_Style.h5')
    BarraDataDF = pd.DataFrame([], columns=['time', 'code'])
    for fac in BarraData.keys():
        factorData = BarraData[fac].stack().reset_index()
        BarraData[fac] = pd.DataFrame([])
        factorData.columns = ['time', 'code', fac]
        if(startdate!=''):
            factorData=factorData[factorData.time>=startdate]
        if(enddate!=''):
            factorData=factorData[factorData.time<=enddate]
        fac = factorData.fillna(0)
        BarraDataDF = BarraDataDF.merge(factorData, on=['time', 'code'], how='outer')
    return BarraDataDF

#模块转换——因子
def factorStack(factor,factorname):
    '''
        factor因子矩阵
        factorname:因子名,string
    '''
    factor=factor.stack().reset_index()
    factor.columns=['time','code',factorname]
    factor['time']=factor['time'].apply(lambda x:str(x))
    return factor

#剔除ST、上市60天以内、停牌股
def kickout(mer):
    # ST状态
    ValidDF=read_feather(Datapath + 'BasicFactor_ValidDF.txt')
    ValidDF['time']=ValidDF['time'].apply(lambda x:int(str(x)[:6]))
    ValidDF=ValidDF.drop_duplicates(subset=['time'],keep='first').set_index('time').stack().reset_index()
    ValidDF.columns=['time','code','valid']
    mer = mer.merge(ValidDF, on=['code', 'time'])
    mer = mer[mer.valid == True]
    del mer['valid']
    return mer

def zscore(x):
    return (x-x.dropna().mean())/x.dropna().std()

def dePCT(x,fac,k1=0.01):
    x.loc[x[fac]>x[fac].quantile(1-k1),fac]=x[fac].quantile(1-k1)
    x.loc[x[fac]<x[fac].quantile(k1),fac]=x[fac].quantile(k1)
    return x
def deSTD(x,fac,k1=2):
    x.loc[x[fac]>x[fac].mean()+x[fac].std()*k1,fac]=x[fac].mean()+x[fac].std()*k1
    x.loc[x[fac]<x[fac].mean()-x[fac].std()*k1,fac]=x[fac].mean()-x[fac].std()*k1
    return x
def deMAD(x,fac,k1=5):
    xmedian=x[fac].median()
    newmad=(x[fac]-xmedian).abs().median()
    x[fac]=np.clip(x[fac],xmedian-k1*newmad,xmedian+k1*newmad)
    return x

def fillmean(x,fac):
    x[fac]=x[fac].fillna(x.mean())
    return x

def fillmedian(x,fac):
    x[fac]=x[fac].fillna(x.median())
    return x
#因子初始化处理
def factorInit(factor):
    factor_list=getfactorname(factor,['time','code'])
    for facname in factor_list:
        factor=factor.groupby('time').apply(deMAD)
        factor=factor.groupby('time').apply(zscore)
    return factor


#获得因子列表
def getfactorname(x,L=['code','time']):
    factor_list=pd.Series(x.columns)
    for l in L:
        try:
            factor_list=factor_list[factor_list!=l]
        except:
            continue
    return factor_list.to_list()

#日频转换为月频率
def dayToMonth(x,factor_list='',method='last'):
    """
    @param x:
    @param method:{'last','mean','sum'}
    """
    x=x.copy()
    if(factor_list==''):
        factor_list=getfactorname(x)
    x=x.pivot(index='time',columns=['code'],values=factor_list)
    x_tmp=pd.DataFrame(index=['time','code']).T
    for fac in factor_list:
        x1=x[fac].reset_index()
        x1['time']=x1['time'].apply(lambda x:int(str(x)[:6]))
        if(method=='sum'):
            x1=x1.groupby('time').sum().stack().reset_index()
            x1.columns=['time','code',fac]
        elif(method=='last'):
            x1=x1.groupby('time').apply(lambda x:x.iloc[-1]).set_index('time').stack().reset_index()
            x1['time']=x1['time'].apply(lambda x:int(x))
            x1.columns=['time','code',fac]
        elif(method=='mean'):
            x1=x1.groupby('time').mean().stack().reset_index()
            x1.columns=['time','code',fac]
        else:
            raise Exception('没有找到该方法')
        x_tmp=x_tmp.merge(x1,on=['time','code'],how='outer')
    return x_tmp

#多空t分组
def longshortfive(x,factor_name,asc=True,t=5):
    x=x.sort_values(factor_name,ascending=asc)['ret']#True是从小到大
    num=x.count()
    div=int(num/t)
    y=pd.Series([])
    for i in range(t-1):
        y[i+1]=x.iloc[div*i:div*(i+1)].mean()
    y[t]=x.iloc[div*(t-1):].mean()
    return y

#筛选出每月指标最大的前k只股票
def selecttopK(x,factor_name,asc=True,k=30):
    x=x.sort_values(factor_name,ascending=asc)['ret']#True是从小到大
    y=pd.Series([])
    y['up']=x.iloc[:k].mean()
    y['down']=x.iloc[-k:].mean()
    y['mean']=x.mean()
    return y


#筛选出每月指标最大的前k%股票
def selecttopKpct(x,factor_name,asc=True,k=0.1):
    x=x.sort_values(factor_name,ascending=asc)['ret']#True是从小到大
    y=pd.Series([])
    num=int(x.shape[0]/k)
    y['up']=x.iloc[:num].mean()
    y['down']=x.iloc[-num:].mean()
    y['mean']=x.mean()
    return y
    
#取残差
def calcResid(y,x1):
    beta=np.linalg.pinv(x1.T.dot(x1)).dot(x1.T).dot(y)
    y_pred=beta.dot(x1.T)
    resid=y-y_pred
    return resid

#加入行业
#加入行业
def addXSWindDum(DF):
    ind_tmp=getIndustryData(freq='month')
    if('SWind' in DF):
        del DF['SWind']
    DF=DF.merge(ind_tmp,on=['time','code'],how='left')
    return DF

def addXSize(DF):
    Size_data=pd.read_feather(Datapath+r'\BasicFactor_DqMV.txt')
    Size_data['time']=Size_data['time'].apply(lambda x:int(str(x)[:6]))
    Size_data=Size_data.fillna(method='ffill').drop_duplicates(['time'],keep='last')
    
    Size_data=Size_data.set_index('time')
    Size_data=Size_data.stack().reset_index()
    Size_data.columns=['time','code','CMV']
    Size_data['CMV']=Size_data['CMV'].apply(lambda x:np.log(x))
    # Size_data=dayToMonth(Size_data)
    if('CMV' in DF):
        del DF['CMV']
    DF=DF.merge(Size_data,on=['time','code'],how='left')
    return DF

def RegbyindSize(x,name):
    #代码补齐
    def zscore(x):
        return (x-x.dropna().mean())/x.dropna().std()
    x_tmp=x[['time','code',name,'SWind','CMV']]
    x_tmp['CMV']=zscore(deMAD(x_tmp,'CMV')['CMV']).fillna(0)
    x_tmp=x_tmp.dropna()    
    if(x_tmp.shape[0]==0):
        x[name+'_neu']=np.nan
        return x
    y=x_tmp[name]
    x1=x_tmp[['CMV']]
    for ind in x['SWind'].unique():
        x_tmp[ind]=0
        x_tmp.loc[x_tmp.SWind==ind,ind]=1
        x1[ind]=x_tmp[ind]  
    x_tmp[name+'_neu']=calcResid(y, x1)
    x=x.merge(x_tmp[['code',name+'_neu']],on='code',how='outer')
    return x

#计算行业市值中性
def calcNeuIndSize(factor,factor_name):
    factor_tmp=factor.copy()
    if('CMV' not in factor):
        factor_tmp=addXSize(factor_tmp)
    if('SWind' not in factor):
        factor_tmp=addXSWindDum(factor_tmp)
    if(factor_name+'_neu' in factor_tmp):
        del factor_tmp[factor_name+'_neu']
    factor_tmp=factor_tmp.groupby('time').apply(RegbyindSize,factor_name).reset_index(drop=True)
    factor=factor.merge(factor_tmp[['time','code',factor_name+'_neu']],on=['time','code'])
    return factor

def addXBarra(DF,Barra_list=''):
    barra_tmp=dayToMonth(getBarraData())
    if(Barra_list==''):
        Barra_list=getfactorname(barra_tmp)        
    if(type(Barra_list)==str):
        Barra_list=[Barra_list]
    DF=DF.merge(barra_tmp[['time','code']+Barra_list],on=['time','code'],how='left')
    return DF,Barra_list
def RegbyBarra(x,name,factor_list):
    #代码补齐
    def zscore(x):
        return (x-x.dropna().mean())/x.dropna().std()
    x_tmp=x[['time','code','SWind',name]+factor_list]
    for fac in factor_list:
        x_tmp[fac]=zscore(deMAD(x_tmp,fac)[fac]).fillna(0)
    x_tmp=x_tmp.dropna()    
    if(x_tmp.shape[0]==0):
        x[name+'_pure']=np.nan
        return x
    y=x_tmp[name]
    x1=x_tmp[factor_list]
    for ind in x['SWind'].unique():
        x_tmp[ind]=0
        x_tmp.loc[x_tmp.SWind==ind,ind]=1
        x1[ind]=x_tmp[ind]  
    x_tmp[name+'_pure']=calcResid(y, x1)
    x=x.merge(x_tmp[['code',name+'_pure']],on='code',how='outer')
    return x

#纯因子
def calcNeuBarra(factor,factor_name,factor_list=''):
    factor_tmp,factor_list=addXBarra(factor,Barra_list=factor_list)
    if('SWind' not in factor):
        factor_tmp=addXSWindDum(factor_tmp)
    if(factor_name+'_pure' in factor_tmp):
        del factor_tmp[factor_name+'_pure']
    factor_tmp=factor_tmp.groupby('time').apply(RegbyBarra,factor_name,factor_list).reset_index(drop=True)
    factor=factor.merge(factor_tmp[['time','code',factor_name+'_pure']],on=['time','code'])
    return factor
#计算IC ——spearmanr 方法
def calcIC(mer, factor_name):
    sp = mer.groupby('time').apply(lambda x: stats.pearsonr(x['ret'], x[factor_name])[0])
    IC = sp.mean()
    ICIR = (sp.mean()) / sp.std() * 12 ** 0.5
   
    sp = mer.groupby('time').apply(lambda x: stats.spearmanr(x['ret'], x[factor_name])[0])
    rankIC = sp.mean()
    rankICIR = (sp.mean()) / sp.std() * 12 ** 0.5
    t_v = sp.mean() / sp.std() * (sp.count() - 1) ** 0.5
    return sp,pd.Series([IC,ICIR,rankIC,rankICIR, t_v],index=['IC:','ICIR:','rankIC:','rankICIR:','t_value:'])
#计算组合业绩




def evaluatePortfolioRet(Rev_seq,t=12):
    """
    @param Rev_seq:
    @param t:天数 默认12(月) 252 日
    @return:
    """
    ret_mean=e**(Rev_seq.apply(lambda x:np.log(x+1)).mean()*t)-1
    ret_sharpe=Rev_seq.mean()*t/Rev_seq.std()/t**0.5
    ret_winrate=Rev_seq[Rev_seq>0].count()/Rev_seq.count()
    ret_maxloss=maxDrawDown(Rev_seq)
    return pd.Series([ret_mean,ret_sharpe,ret_winrate,ret_maxloss],index=['年化收益率:','信息比率:','胜率:','最大回撤:'])
# 更新数据库信息
def DataRenewTime():
    datainfo = pd.read_excel(DataInfopath)
    for i in datainfo.index:
        if (os.path.exists(Datapath + datainfo.loc[i, '存储地址'])):
            datainfo.loc[i, '最新时间'] = int(read_feather(Datapath + datainfo.loc[i, '存储地址'])['time'].max())
        else:
            datainfo.loc[i, '最新时间'] = np.nan
    datainfo.to_excel(DataInfopath, index=False)
  
# 更新factor最新信息
# 获得开始更新时间
def getUpdateStartTime(x, backdays=0):
    '''
      backdays是回退天数
      日频使用1日
      更低频率anndt等使用5日
    '''
    if (x.count() != len(x)):
        return g_starttime
    else:
        return (datetime.datetime.strptime(str(int(x.min())), '%Y%m%d') - datetime.timedelta(days=backdays)).strftime(
            '%Y%m%d')

def readLocalData(rawpath,key=''):
    """
       param:path 路径  key 键名
    """
    path=Datapath+rawpath
    if(os.path.exists(path)):
        data=read_feather(path)
        data=data.set_index('time')
        data=data.unstack().reset_index()
        if(key==''):
            datainfo=pd.read_excel(DataInfopath)
            key=datainfo[datainfo['存储地址']==rawpath].iloc[0]['数据库键']
        data.columns=['code','time',key]
        data=data[['time','code',key]]
    else:
        data=pd.DataFrame(index=['time','code']).T
    return data

#批量读入
def readLocalDataSet(path_list):
    data_tot=pd.DataFrame(index=['time','code']).T
    for path in path_list:
       data_tot=data_tot.merge(readLocalData(path),on=['time','code'],how='outer') 
    return data_tot
#合并新旧信息，
def mergeAB(rawData,newData):
    """
    """
    #检查新信息最新行的空值率
    #    if(newData[newData.time==newData.time.max()].groupby('time').count().iloc[-1,-1]==0):
    #        print( Exception('最后一行为空'))
    #目前采用后值覆盖方法，假定后值正确
    if(rawData.shape[0]>0):
        rawData0=rawData[rawData.time<newData['time'].min()]
        rawData=rawData[rawData.time>=newData['time'].min()]
    else:
        rawData0=rawData
    rawData=rawData.append(newData).drop_duplicates(subset=['time','code'],keep='last')
    rawData=rawData0.append(rawData)
    return rawData

def readLocalFeather(path):
    if(os.path.exists(Datapath+path)):
        return read_feather(Datapath+path)
    else:
        return pd.DataFrame(index=['time','code']).T


#用于存储sql型数据
def saveSqlData(sqlData,infoDF):
    if(os.path.exists(path)):
        data=read_feather(path)
    else:
        data=pd.DataFrame([])  
    #把sqlData最后一部分拿出来， drop  
    data0=data[data.time<sqlData['time'].min()]
    data=data[data.time>=sqlData['time'].min()]
    data=data.append(sqlData).drop_duplicates(subset=['time','code'],keep='last').sort_values(by='time')
    data0=data0.append(data)
    save_feather(Datapath+infoDF.loc[i,'存储地址'],data0.pivot(index='time',columns='code',values=infoDF.loc[i,'数据库键']).reset_index())
#存储日频数据
def saveDailyData(sqlData,infoDF):
     for i in infoDF.index:
        sql_data1=sqlData[['time','code',infoDF.loc[i,'数据库键']]].pivot(index='time',columns='code',values=infoDF.loc[i,'数据库键']).reset_index()
        data0=readLocalFeather(infoDF.loc[i,'存储地址'])
        data0=data0.append(sql_data1)
        data0['time']=data0['time'].apply(lambda x:int(x))
        if('code' in data0):
            del data0['code']
        save_feather(Datapath+infoDF.loc[i,'存储地址'],data0.drop_duplicates(subset='time',keep='last').sort_values(by='time'))

#用于存储财务数据
def saveFinData(sqlData,infoDF):
     for i in tqdm(infoDF.index):
        sql_data1=sqlData[['time','code',infoDF.loc[i,'数据库键']]].drop_duplicates(subset=['time','code'],keep='last').pivot(index='time',columns='code',values=infoDF.loc[i,'数据库键'])
        data0=readLocalFeather(infoDF.loc[i,'存储地址']).set_index('time',drop=True)
        data0=data0.append(sql_data1).reset_index()
        data0['time']=data0['time'].apply(lambda x:int(x))
        data0=data0.drop_duplicates(subset='time',keep='last')
        if('code' in data0):
            del data0['code']
        save_feather(Datapath+infoDF.loc[i,'存储地址'],data0)
#用于存储成分股数据
def saveIndData(sqlData,infoDF):
     for i in infoDF.index:
         sqlData1=sqlData[['time','code',infoDF.loc[i,'数据库键']]]
         sqlData2=sqlData[['eddate','code']].dropna()
         sqlData2.columns=['time','code']
         sqlData2['out']=-1
         sqlData=sqlData1.merge(sqlData2,on=['time','code'],how='outer').drop_duplicates(subset=['time','code'],keep='first')     
         sqlData.loc[sqlData[infoDF.loc[i,'数据库键']]!=sqlData[infoDF.loc[i,'数据库键']],infoDF.loc[i,'数据库键']]=sqlData.loc[sqlData[infoDF.loc[i,'数据库键']]!=sqlData[infoDF.loc[i,'数据库键']],'out']
         del sqlData['out']
         
         data0=readLocalFeather(infoDF.loc[i,'存储地址']).set_index('time')
         data0=data0.append(sqlData.pivot(index='time',columns='code',values=infoDF.loc[i,'数据库键'])).reset_index()
         data0['time']=data0['time'].apply(lambda x:int(x))
         data0=data0.drop_duplicates(subset='time',keep='last').set_index('time').reindex(index=getTradeDateList(),columns=getStockList()).fillna(method='ffill').reset_index()
         data0.replace({-1:np.nan},inplace=True)
         if('code' in data0):
             del data0['code']
         save_feather(Datapath+infoDF.loc[i,'存储地址'],data0)
         

#调试
def saveIndexComponentData(sqlData,infoDF):
    i=infoDF.index[0]
    sqlData.columns=['time','code','signal']        
    sqlData['time']=sqlData['time'].apply(lambda x:x.strftime('%Y%m%d'))
    data0=readLocalFeather(infoDF.loc[i,'存储地址']).set_index('time')
    data0=data0.append(sqlData.pivot(index='time',columns='code',values='signal')).reset_index()
    data0['time']=data0['time'].apply(lambda x:int(x))
    data0=data0.drop_duplicates(subset='time',keep='last').set_index('time').fillna(method='ffill').reindex(index=getTradeDateList(),columns=getStockList()).fillna(method='ffill').reset_index()  
    data0.replace({'剔除':np.nan,'纳入':1},inplace=True)
    if('code' in data0):
        del data0['code']
    save_feather(Datapath+infoDF.loc[i,'存储地址'],data0)

def partition(ls, size):
    """
    Returns a new list with elements
    of which is a list of certain size.

        >>> partition([1, 2, 3, 4], 3)
        [[1, 2, 3], [4]]
    """
    return [ls[i:i+size] for i in range(0, len(ls), size)]


#def getFisicalList(period='Season'):
#    data=read_feather(Datapath+'BasicFactor_AShareFinancialIndicator_ANN_DT.txt')
#    datelist=pd.Series(data['time'].apply(lambda x:int(str(x))).unique(),name='time')
#    datelist=datelist[datelist.apply(lambda x:str(x)[-4:]).isin(['0331','0630','0930','1231'])]
#    if(period=='year'):
#        return datelist[datelist.apply(lambda x:str(x)[-4:]=='1231')]
#    else:
#        return datelist[datelist>=19921231]
    
    
def getFisicalList(period='Season'):
    data=read_feather(Datapath+'BasicFactor_AShareFinancialIndicator_ANN_DT.txt')
    
    year_list=pd.Series(data['time'].apply(lambda x:int(str(x)[:4])).unique(),name='time')
    if(period=='year'):
        return year_list.apply(lambda x:int(str(x)+'1231'))
    else:
        monthlist=[]
        for year in year_list:
            for season in ['0331','0630','0930','1231']:
                monthlist.append(int(str(year)+season))
        monthlist=pd.Series(monthlist)
        return monthlist[monthlist>=19891231]
'''
lxy新增FB内容
'''    


'''
计算每季度数据
'''
    
def convFisicalQFA(Fa):#Fa为文件路径(要注意数据是否能够进行QFA操作，数据初始间隔需要为一季度)
    df=read_feather(Fa)
    df['time']=df['time'].astype(int)
    df=df.set_index('time').reindex(getFisicalList()).iloc[1:]
    tempt2=pd.DataFrame()
    for i in range(int(len(df)/4)):
        tempt=df.iloc[4*i:4*(i+1)]
        tempt1=pd.DataFrame()
        tempt1=tempt-tempt.shift(1)
        tempt1.iloc[0]=tempt.iloc[0]
        tempt2=tempt2.append(tempt1)
    
    return tempt2
         
'''
计算最近十二个月数据
'''         

def convFisicalTTM(Fa):#Fa为文件路径(注意数据能否能够进行TTM操作，数据初始间隔需要为一季度)
    df=read_feather(Fa)
    df['time']=df['time'].astype(int)
    df=df.set_index('time').reindex(getFisicalList()).iloc[1:]
    tempt2=pd.DataFrame()
    for i in range(int(len(df)/4)-1):
        tempt=df.iloc[4*i:4*(i+2)]
        tempt1=pd.DataFrame()
        tempt1=tempt-tempt.shift(4)+tempt.iloc[3]
        tempt1=tempt1.iloc[4:]
        tempt2=tempt2.append(tempt1)
    
    tempt2=tempt2.reset_index()
    tempt2=tempt2.rename(columns={'index':'time'})
    return tempt2

'''
计算同比增长率
'''
def convFisicalYOY(Fa):#Fa为文件路径(要注意数据是否能够进行YOY操作)
    df=read_feather(Fa)
    df['time']=df['time'].astype(int)
    df=df.set_index('time').reindex(getFisicalList()).iloc[1:]
    tempt2=pd.DataFrame()
    for i in range(int(len(df)/4)-1):
        tempt=df.iloc[4*i:4*(i+2)]
        tempt1=pd.DataFrame()
        tempt1=(tempt-tempt.shift(4))/tempt.shift(4)
        tempt1=tempt1.iloc[4:]
        tempt2=tempt2.append(tempt1)
        
    tempt2=tempt2.reset_index()
    tempt2=tempt2.rename(columns={'index':'time'})
    
    return tempt2


'''
计算变化率，默认为how=up即：本期/上一期，how=down为上一期/本期
'''
def convFisicalROC(Fa,how='up'):
    df=read_feather(Fa)
    df['time']=df['time'].astype(int)
    df=df.set_index('time').reindex(getFisicalList()).iloc[1:]
    if how=='up':
        tempt=df/df.shift(1)
    if how=='down':
        tempt=df/df.shift(-1)
    tempt=tempt.reset_index()
    tempt=tempt.rename(columns={'index':'time'})
    
    return tempt
    
 
'''
储存中心化后的三列式数据，可输入地址，也可输入矩阵形式（注：随意做的，如果需要，建议自己重新写一个）
'''
   
def saveHeatData(path,key='',needtrans=True):
    if type(path)==str:
        df=FB.read_feather(path)
    else:
        df=path.reset_index()
    if needtrans==True:
        df=FB.transData(df,key)
    else:
        df=df.set_index('time').stack().reset_index()
        df.columns=['time','code',key]
        df=df[df.time>=201001]
        df=df[df.time<=202112]
    df=df.groupby('time').apply(FB.deMAD,key)
    df=FB.calcNeuIndSize(df,key)
    df=df[['time','code',key+'_neu']]
    df=df.dropna()
    FB.save_feather(Factorpath+key+'_neu.txt',df)

    return df
    
'''
将原始数据与公布时间相结合（注：这个函数和下一个seasonToMonth的函数合并为了最下方transData函数）（保留是为了特殊情况下使用，可忽略。）
'''

def mergeANN(rawpath,key=''):#rawpath可以是文件路径也可以是矩阵形式，如果输入的是矩阵需要保证第一列为time，第二列为level_1，默认的key为factor，最后得到的矩阵分为4列，code、time、ANN_DT、key
    if type(rawpath) is str:
        if(key==''):
            key='factor'
        ANN_DT=read_feather(Datapath + 'BasicFactor_AShareFinancialIndicator_ANN_DT.txt').set_index('time').stack().reset_index().set_index('level_1').astype(int).reset_index()
        data=read_feather(Datapath+rawpath).set_index('time').stack().reset_index()
        df=pd.merge(ANN_DT,data,on=['time','level_1'])
        df.columns=['code','time','ANN_DT',key]
        df.dropna(subset=['ANN_DT'],inplace=True)
        return df
    else:  
        if(key==''):
            key='factor'
        ANN_DT=read_feather(Datapath + 'BasicFactor_AShareFinancialIndicator_ANN_DT.txt').set_index('time').stack().reset_index().set_index('level_1').astype(int).reset_index()
        df=pd.merge(ANN_DT,rawpath,on=['time','level_1'])
        df.columns=['code','time','ANN_DT',key]
        df.dropna(subset=['ANN_DT'],inplace=True)
        return df


'''
将原本间隔为每季度的数据间隔减少为每月        
'''
def seasonToMonth(df):#df的格式要求为四列：code、time、ANN_DT、数据,最后得到的为三列，time、code、数据
    
    factorDF=df.copy()
    key=factorDF.columns[3]
    monthlist=getTradeDateList('month')
    factorDF.dropna(subset=['ANN_DT'],inplace=True)
    factorDF['rtime']=factorDF['ANN_DT'].apply(lambda x:int(str(x)[:6]))
    factorDF=factorDF.drop_duplicates(subset=['code','rtime'],keep='last')
    factorDF_loc=factorDF.pivot(index='rtime',columns='code',values= key)
    factorDF_loc=factorDF_loc.reindex(monthlist[monthlist>=factorDF_loc.index[0]]).fillna(method='ffill')
    factorDF=factorDF_loc.stack().reset_index()
    factorDF.rename(columns={0:key},inplace=True)
    return factorDF




#输入的data需要为矩阵形式,index为序号，有一列为time，columns为code，默认的key为factor，output默认为三列式，如果output=‘matrix’可以输出矩阵
def transData(data,key='factor',output='',startMonth=201001,endMonth=202112,method='ffill'):
    ANN_DT=read_feather(Datapath + 'BasicFactor_AShareFinancialIndicator_ANN_DT.txt').set_index('time').stack().reset_index().set_index('level_1').astype(int).reset_index()
    data=data.set_index('time').stack().reset_index()
    factorDF=pd.merge(ANN_DT,data,on=['time','level_1'])
    factorDF.columns=['code','time','ANN_DT',key]
    monthlist=getTradeDateList('month')
    factorDF['rtime']=factorDF['ANN_DT'].apply(lambda x:int(str(x)[:6]))
    factorDF=factorDF.drop_duplicates(subset=['code','rtime'],keep='last')
    factorDF_loc=factorDF.pivot(index='rtime',columns='code',values= key)
    if method=='ffill':
        factorDF_loc=factorDF_loc.reindex(monthlist[monthlist>=factorDF_loc.index[0]]).fillna(method='ffill')
    if method=='bfill':
        factorDF_loc=factorDF_loc.reindex(monthlist[monthlist>=factorDF_loc.index[0]]).fillna(method='bfill')        
    factorDF=factorDF_loc.stack().reset_index()
    factorDF.rename(columns={0:key},inplace=True)
    factorDF=factorDF[factorDF.time>=startMonth]
    factorDF=factorDF[factorDF.time<=endMonth]
    if output=='matrix':
        return factorDF.pivot(index='time',columns='code',values=key)
    else:
        return factorDF

#装饰器——————————————————————————————————————————————————————
#测时
def testTime(func):
    def test(*args,**kwargs):
        starttime=time.time()
        func(*args,**kwargs)
        endtime=time.time()
        print('用时：',round((endtime-starttime) * 1000),'ms')
    return test

#    @staticmethod  内置函数
#    @property  1. 方法——》属性    2. self._A=1    设置self.A() return self._A  防止_A被修改
#    @classmethod 通过类名直接调用函数


